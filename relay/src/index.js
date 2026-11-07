// The pyrogue co-op relay. Each game is a room, named by the code the host picked, and lives
// in one Durable Object. The host and every player connect to it with a WebSocket.
//
// Every message is "<player id>|<payload>", in both directions:
//   player -> host:  the room adds the sender's id: "3|{...}"
//   host -> player:  "3|{...}" is sent on to player 3 as "{...}"
//   "3|+" tells the host player 3 arrived, "3|-" that they left; a host sending "3|-" drops them.
// Payloads aren't read here, so the relay never needs to change with the game.

import { DurableObject } from 'cloudflare:workers';

const CODE = /^[A-Z0-9]{4,12}$/;
const MAX_PLAYERS = 8;              // the game takes 4; a few more can be turned away politely

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const match = url.pathname.match(/^\/room\/([^/]+)$/);
    if (!match) {
      return new Response('pyrogue co-op relay\n');
    }
    const code = match[1].toUpperCase();
    if (!CODE.test(code)) {
      return new Response('A room code is 4 to 12 letters and digits.', { status: 400 });
    }
    if (request.headers.get('Upgrade') !== 'websocket') {
      return new Response('Connect with a WebSocket.', { status: 426 });
    }
    return env.ROOMS.get(env.ROOMS.idFromName(code)).fetch(request);
  },
};

export class Room extends DurableObject {
  async fetch(request) {
    const host = this.ctx.getWebSockets('host')[0];
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);
    if (new URL(request.url).searchParams.get('role') === 'host') {
      if (host) {
        return new Response('That room code is already taken. Try another.', { status: 409 });
      }
      this.ctx.acceptWebSocket(server, ['host']);
    } else {
      if (!host) {
        return new Response('Nobody is hosting a game with that code.', { status: 404 });
      }
      if (this.ctx.getWebSockets('player').length >= MAX_PLAYERS) {
        return new Response('That game is full.', { status: 403 });
      }
      const id = ((await this.ctx.storage.get('next')) || 0) + 1;
      await this.ctx.storage.put('next', id);
      this.ctx.acceptWebSocket(server, ['player', `p${id}`]);
      server.serializeAttachment({ id });
      host.send(`${id}|+`);
    }
    return new Response(null, { status: 101, webSocket: client });
  }

  webSocketMessage(ws, data) {
    if (typeof data !== 'string') {
      return;
    }
    if (this.ctx.getTags(ws).includes('host')) {
      const bar = data.indexOf('|');
      const [player] = this.ctx.getWebSockets(`p${data.slice(0, bar)}`);
      if (!player) {
        return;
      }
      const payload = data.slice(bar + 1);
      if (payload === '-') {
        player.close(1000, 'The host closed the connection.');
      } else {
        player.send(payload);
      }
    } else {
      const host = this.ctx.getWebSockets('host')[0];
      if (host) {
        host.send(`${ws.deserializeAttachment().id}|${data}`);
      }
    }
  }

  webSocketClose(ws) {
    this.gone(ws);
  }

  webSocketError(ws) {
    this.gone(ws);
  }

  gone(ws) {
    try {
      ws.close(1000, 'Goodbye.');
    } catch {
      // already closed
    }
    if (this.ctx.getTags(ws).includes('host')) {
      for (const player of this.ctx.getWebSockets('player')) {
        player.close(1000, 'The host closed the game.');
      }
      this.ctx.storage.deleteAll();
    } else {
      const host = this.ctx.getWebSockets('host')[0];
      if (host) {
        host.send(`${ws.deserializeAttachment().id}|-`);
      }
    }
  }
}

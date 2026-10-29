"""Talking to the friendly characters (&)."""

import curses
import random
import textwrap

from .characters import LORE, SONGS
from .constants import FINAL_DEPTH, MAX_PACK
from .items import Item, POTIONS, SCROLLS
from .monsters import WEAK_SPOTS
from .moves import MAX_SPELLS, MOVES, SPELLS
from .text import COLORS, an


class TalkMixin:
    """Talking to the friendly characters (&)."""

    def talk(self, npc):
        getattr(self, 'talk_' + npc.kind)(npc)
        npc.talked += 1
        self.compute_fov()

    def npc_say(self, npc, text):
        lines = textwrap.wrap(text, 72) or ['']
        for i in range(0, len(lines), 2):
            self.draw_dialog(npc, lines[i:i + 2], more=True)
            self.wait_key()

    def npc_ask(self, npc, text, options):
        """Ask a question with a cursor menu. Esc picks the last option."""
        lines = textwrap.wrap(text, 72)[:2]
        i = self.select(lambda cur: self.draw_dialog(npc, lines, options=options, cur=cur),
                        len(options))
        return len(options) - 1 if i is None else i

    def draw_dialog(self, npc, text, more=False, options=None, cur=0):
        self.draw([], refresh=False)
        self.box(9, 1, 7, 18)
        for i, line in enumerate(npc.portrait):
            self.put(10 + i, 3, line, COLORS[npc.color] | curses.A_BOLD)
        self.box(16, 0, 8, 80)
        self.put(16, 3, f' {npc.name} ', COLORS[npc.color] | curses.A_BOLD | curses.A_REVERSE)
        for i, line in enumerate(text):
            self.put_rich(18 + i * 2, 3, line)
        if more:
            self.put(21, 76, '▼', curses.A_BOLD | curses.A_BLINK)
        if options:
            w = max(len(o) for o in options) + 5
            top = 16 - len(options) - 2
            self.box(top, 79 - w, len(options) + 2, w)
            for i, o in enumerate(options):
                self.put(top + 1 + i, 81 - w, ('▶' if i == cur else ' ') + o,
                         curses.A_BOLD if i == cur else 0)
        self.scr.refresh()

    def give_item(self, npc, it):
        if it.sub:
            self.known.add(it.sub)
        name = self.item_name(it)
        if self.add_to_pack(it):
            self.npc_say(npc, f'{self.name} received {name}!')
        else:
            p = self.player
            it.x, it.y, it.seen = p.x, p.y, True
            self.items.append(it)
            self.npc_say(npc, f'Your pack is full, so {name} was put on the floor.')

    def talk_sage(self, npc):
        say = lambda t: self.npc_say(npc, t)
        if not npc.talked:
            say(f'Ah, a new face! Welcome, {self.name}. Few adventurers come down here anymore.')
            say('Monsters lurk in these halls. Walk into one, or let one catch you, '
                'and you will be drawn into BATTLE!')
            say(f'Somewhere far below, on depth {FINAL_DEPTH}, the Frost Wyrm guards the '
                'Amulet of Yendor. Bring it back and you will be a legend.')
            say('And mind your step! Hidden traps lurk in these halls. Search (s) and you '
                'may spot them before they spot you.')
            say('Here, take these. You will need them more than I do.')
            self.give_item(npc, Item('potion', 'healing'))
            self.give_item(npc, Item('scroll', 'FIRE BOLT'))
            say('Read that spell scroll from your inventory (i) and you will learn FIRE BOLT. '
                'Spell scrolls are rare, so treasure any you find!')
        while True:
            c = self.npc_ask(npc, 'Is there anything else you wish to know?',
                             ['Battles', 'Moves & types', 'The road ahead', 'Friendly folk',
                              'Goodbye'])
            if c == 0:
                say('In battle you may FIGHT, open your BAG, GUARD to halve the next blow, '
                    'or try to RUN. Running works best against weaker foes.')
                say('When you STRIKE or POWER SMASH, you choose where to hit. The HEAD is hard '
                    'to hit but hurts more, and every monster has a weak spot somewhere.')
                say('Hit a weak spot once and you will remember it for every monster of that '
                    'kind. It is never the BODY, so be bold!')
                say('A monster you escape from is dazed for a few turns. Use them well!')
                say('Battles are noisy, and every round is a turn in the dungeon. Fight too '
                    'long and other monsters will join in!')
            elif c == 1:
                say('You know STRIKE and POWER SMASH. New spells come only from rare spell '
                    f'scrolls, and you can hold {MAX_SPELLS} spells at most. Learn another and '
                    'you must forget one.')
                say('Swords and maces make your STRIKEs hit harder. Wands and staffs barely '
                    'scratch a foe, but they make every spell you cast hit harder.')
                say('FIRE scorches beasts and giants, but dragons shrug it off. HOLY light '
                    'sears the undead. Weak spots hurt, but they will not win a fight alone.')
                say('Every spell costs mana (MP). It slowly returns as you walk and rest, '
                    'and comes back in full when you grow a level.')
                say('Many spells leave a mark: burns and poison hurt every turn, while sleep, '
                    'frost and paralysis can make a foe lose its turn.')
                say('Monsters can do the same to you! A potion of healing or a healer will '
                    'cure what ails you.')
            elif c == 2:
                say(f'The way down is {FINAL_DEPTH} levels deep, through four lands: the Dungeons '
                    'of Doom, the Sunken Catacombs, the Ember Caverns and the Frozen Abyss.')
                say('At depth 10 the BONE KING seals the way down. At the very bottom the FROST '
                    'WYRM coils around the Amulet. Neither will let you run away!')
                say('Bosses grow desperate when wounded. Save your mana and potions for them.')
            elif c == 3:
                say('Look for the & sign on deeper floors. Every other floor, a merchant waits '
                    'by the stairs down to trade for gold.')
                say('Others are rarer: healers mend wounds, bards know many secrets, a smith '
                    'can improve your weapon and armor, and a mage teaches spells.')
                say('And in the Catacombs, they say the dead still whisper of what they '
                    'learned too late...')
            else:
                say('Good luck down there!')
                return

    def talk_merchant(self, npc):
        p = self.player
        say = lambda t: self.npc_say(npc, t)
        say('Welcome, welcome! Pip has the finest wares in all the dungeon!' if not npc.talked
            else 'Back again, friend? Wonderful!')
        while True:
            c = self.npc_ask(npc, f'What will it be? (You have {p.gold} gold.)',
                             ['Buy', 'Sell', 'Goodbye'])
            if c == 0:
                if not npc.stock:
                    say("I'm all sold out! Come back... well, never, I suppose.")
                    continue
                opts = [f'{self.item_name(it, reveal=True)[:38]:<38} {self.price(it):>4}g'
                        for it in npc.stock] + ['Back']
                i = self.npc_ask(npc, f'Take a look! (You have {p.gold} gold.)', opts)
                if i == len(npc.stock):
                    continue
                it = npc.stock[i]
                cost = self.price(it)
                if p.gold < cost:
                    say("Ah, you can't afford that, I'm afraid.")
                elif len(p.pack) >= MAX_PACK:
                    say('Your pack is full! Sell me something first.')
                else:
                    p.gold -= cost
                    npc.stock.remove(it)
                    self.give_item(npc, it)
                    say('Pleasure doing business!')
            elif c == 1:
                sold = self.sell_screen(npc)
                if sold is None:
                    say("You've nothing I can use, friend. I don't take what you're wearing!")
                else:
                    say(f'Done and done! That is {sold} gold for you.' if sold else
                        'Nothing catch your fancy? No matter!')
            else:
                say('Come back anytime!')
                return

    def offer(self, it):
        """What a merchant pays for one of an item."""
        return max(1, self.price(it) // 3)

    def sell_screen(self, npc):
        """Sell from the inventory screen, one thing after another. Returns the gold made,
        or None if there is nothing the merchant will buy."""
        p = self.player
        sellable = lambda it: it is not p.weapon and it is not p.armor
        if not any(map(sellable, p.pack)):
            return None
        made = [0]

        def sell(choice, view):
            it = choice[1]
            each, n = self.offer(it), it.count
            labels = ([f'Sell one ({each}g)', f'Sell all {n} ({each * n}g)'] if n > 1 else
                      [f'Sell it ({each}g)']) + ['Back']
            i = self.select(lambda c: self.draw_inventory(
                *view, ' up/down: choose   Enter: pick   Esc: back',
                f'{npc.name} pays {each} gold' + (' apiece.' if n > 1 else '.'),
                actions=(labels, c)), len(labels))
            if i is None or i == len(labels) - 1:
                return False, None, None
            qty = n if i == 1 else 1
            it.count = qty
            name = self.item_name(it)                 # what is being sold, for the log
            it.count = n
            for _ in range(qty):
                self.use_up(it)
            p.gold += each * qty
            made[0] += each * qty
            self.record(f'You sold {name} for {each * qty} gold.')
            return False, None, f'Sold {name} for {each * qty} gold! What else?'

        price = lambda it: f'{self.offer(it)}g' + (' each' if it.count > 1 else '')
        self.browse(lambda: self.inventory_rows(False, sellable, price), sell,
                    f' SELL TO {npc.name}', ' up/down: move   letter/Enter: sell   Esc: done')
        return made[0]

    def talk_healer(self, npc):
        p = self.player
        say = lambda t: self.npc_say(npc, t)
        cost = 0 if not npc.done else 20 + self.depth * 8
        if not npc.talked:
            say('Peace be with you, traveler. You look weary from the road.')
        price = 'free, this once' if cost == 0 else f'{cost} gold'
        if self.npc_ask(npc, f'Shall I tend to your wounds? ({price})',
                        ['Yes, please', 'No, thank you']) != 0:
            say('Then go with care.')
            return
        if p.gold < cost:
            say(f'I am sorry, child. The temple asks {cost} gold for its blessings.')
            return
        p.gold -= cost
        npc.done = True
        p.hp, p.str = p.max_hp, p.max_str
        p.cure()
        p.restore_mp()
        say('A warm light surrounds you... HP and MP fully restored!')

    def talk_bard(self, npc):
        p = self.player
        say = lambda t: self.npc_say(npc, t)
        if not npc.talked:
            say('Ho there! Finch the Bard, at your service. I collect songs and secrets.')
        cost = 40 + self.depth * 5
        while True:
            c = self.npc_ask(npc, 'What would you like to hear?',
                             ['A song', 'Some advice', f'A secret ({cost}g)', 'Goodbye'])
            if c == 0:
                for line in random.choice(SONGS):
                    say(line)
            elif c == 1:
                say(random.choice(LORE))
            elif c == 2:
                unknown = [k for k in POTIONS + SCROLLS if k not in self.known]
                if npc.done:
                    say("I've told you my best secret already. A bard must keep some mystery!")
                elif not unknown:
                    say('You already know every secret I have!')
                elif p.gold < cost:
                    say(f'Secrets cost coin, friend. Come back with {cost} gold.')
                else:
                    p.gold -= cost
                    npc.done = True
                    # the most useful secret first: which scrolls identify the rest
                    kind = 'identify' if 'identify' in unknown else random.choice(unknown)
                    self.known.add(kind)
                    if kind in POTIONS:
                        say(f'Psst... the {self.potion_look[kind]} potions? '
                            f'Those are potions of {kind}.')
                    else:
                        say(f'Psst... scrolls titled "{self.scroll_look[kind]}"? '
                            f'Those are scrolls of {kind}.')
            else:
                say('Farewell! May your tale be worth a song.')
                return

    def talk_hermit(self, npc):
        say = lambda t: self.npc_say(npc, t)
        if npc.done:
            say('Bless you for the food, friend. My belly still sings your praises.')
            return
        say('Food... have you any food? I have not eaten in days...')
        food = next((i for i in self.player.pack if i.kind == 'food'), None)
        if not food:
            say('No? Ah, well. Come back if you find some...')
            return
        if self.npc_ask(npc, 'Will you share a food ration?', ['Give food', 'Sorry, no']) != 0:
            say('*sigh* I understand. Times are hard.')
            return
        self.use_up(food)
        npc.done = True
        say('Oh, thank you, thank you! Here, I found this long ago. It is no use to an old man.')
        self.give_item(npc, Item('scroll', random.choice(['enchant weapon', 'enchant armor'])))

    def talk_smith(self, npc):
        p = self.player
        say = lambda t: self.npc_say(npc, t)
        if not npc.talked:
            say('Hah, a customer! Bram the Smith. There is nothing down here I cannot hammer '
                'into better shape.')
        cost = 50 + self.depth * 10
        while True:
            c = self.npc_ask(npc, f'Each piece once, {cost} gold apiece. (You have {p.gold} gold.)',
                             ['Improve my weapon', 'Reinforce my armor', 'Goodbye'])
            if c == 2:
                say('Keep that edge sharp!')
                return
            slot = ('weapon', 'armor')[c]
            gear = p.weapon if slot == 'weapon' else p.armor
            if not gear:
                say(f'You have no {slot} on you! I cannot work on thin air.')
            elif slot in npc.used:
                say('I have done all I can for that. Any more and it would crack!')
            elif p.gold < cost:
                say(f'Good steel costs good coin. Come back with {cost} gold.')
            else:
                p.gold -= cost
                npc.used.add(slot)
                gear.ench += 1
                if slot == 'weapon':
                    say(f'*CLANG* *CLANG* Your {gear.sub} is better than ever! {self.weapon_note()}')
                else:
                    say(f'*CLANG* *CLANG* Your {gear.sub} is sturdier now. Your defense is {p.ac}.')
                self.record(f'Bram the Smith improved your {gear.sub}.')

    def talk_arcanist(self, npc):
        p = self.player
        say = lambda t: self.npc_say(npc, t)
        if not npc.talked:
            say('Mage Oriel, scholar of the deep arts. I teach spells, for a fee. Knowledge is '
                'never free, and scrolls are so very rare.')
        mana_cost = 15 + self.depth * 3
        while True:
            c = self.npc_ask(npc, f'What do you seek? (You have {p.gold} gold.)',
                             ['Learn a spell', f'Restore my mana ({mana_cost}g)', 'Goodbye'])
            if c == 0:
                lessons = [s for s in npc.stock if s not in p.moves]
                if not lessons:
                    say('You already know everything I can teach you.')
                    continue
                opts = [f'{s:<16} {MOVES[s]["type"].upper():<8} {SPELLS[s][1]:>4}g'
                        for s in lessons] + ['Back']
                i = self.npc_ask(npc, 'Which spell shall I teach you? '
                                 f'(You know {len(p.spells)} of {MAX_SPELLS}.)', opts)
                if i == len(lessons):
                    continue
                spell = lessons[i]
                cost = SPELLS[spell][1]
                if p.gold < cost:
                    say(f'That lesson costs {cost} gold. Come back when your purse is heavier.')
                    continue
                if len(p.spells) >= MAX_SPELLS:
                    old = self.pick_forget(spell)
                    if not old:
                        say('Make room in that head of yours first, then.')
                        continue
                    p.moves.remove(old)
                    say(f'First we must clear the mind... {self.name} forgot {old}.')
                p.gold -= cost
                p.moves.append(spell)
                say(f'Repeat after me... Good! {self.name} learned {spell}!')
                self.record(f'Mage Oriel taught you {spell}.')
            elif c == 1:
                if p.mp >= p.max_mp:
                    say('Your mana is already full to the brim.')
                elif p.gold < mana_cost:
                    say(f'Even mana has its price. {mana_cost} gold, please.')
                else:
                    p.gold -= mana_cost
                    p.restore_mp()
                    say('Oriel touches your brow, and power floods back in. MP fully restored!')
            else:
                say('May your spells fly true.')
                return

    def talk_ghost(self, npc):
        say = lambda t: self.npc_say(npc, t)
        say('Ooooh... another living soul, wandering my tomb...')
        say('I fell here long ago. Too late I learned where these creatures are weakest. '
            'Let my knowledge serve you better...')
        names = sorted({t[1] for t in self.eligible_monsters()} - self.weak_known)
        secrets = random.sample(names, min(3, len(names)))
        if not secrets:
            say('But you already know all that I knew. Go in peace...')
        for name in secrets:
            self.weak_known.add(name)
            say(f'The {name.upper()}... strike at its {WEAK_SPOTS[name]}.')
            self.record(f'The spirit whispered: {an(name)} is weak in its {WEAK_SPOTS[name]}.')
        say('Avenge me... The spirit fades away into the cold stone.')
        self.npcs.remove(npc)

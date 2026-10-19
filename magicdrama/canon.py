import json
import pathlib

def load_canon():
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "canon_e01_e10.json"
    return json.loads(p.read_text())

CANON = load_canon()

CANON_FACTS = [['f01', 'second_period', '1', 'character', 'mina', 'is_a', 'ex-idol trainee turned substitute music teacher', '1', '', 'canon', 'audience', '1', 'junho:1', 'revealed', 'high', 'none', '', 'accepted'], ['f02', 'second_period', '2', 'character', 'han', 'holds', "mina's file and knows her past", '2', '', 'canon', 'audience', '2', 'han:2', 'revealed', 'high', 'none', '', 'accepted'], ['f03', 'second_period', '5', 'character', 'junho', 'song_uses', "mina's stolen melody, given by han", '5', '', 'canon', 'audience', '5', 'junho:5 mina:5', 'revealed', 'high', 'none', '', 'accepted'], ['f04', 'second_period', '6', 'event', 'han_cut_mina', 'flashback', 'han cut mina from the agency', '6', '', 'canon', 'audience', '6', 'han:6 mina:6', 'revealed', 'high', 'none', '', 'accepted'], ['f05', 'second_period', '8', 'event', 'voice_memo', 'proves', 'taeyang took the song and han knew', '8', '', 'canon', 'audience', '8', 'junho:8 mina:8 ari:8', 'revealed', 'high', 'none', '', 'accepted'], ['f06', 'second_period', '10', 'event', 'han_exposed', 'outcome', 'truth surfaces, han is exposed, mina keeps teaching', '10', '', 'canon', 'audience', '10', 'all:10', 'revealed', 'high', 'none', '', 'accepted'], ['f07', 'second_period', '10', 'thread', 'comeback_offer', 'open', 'taeyang offers mina a real comeback', '10', '', 'canon', 'audience', '10', 'mina:10 taeyang:10', 'open', 'high', 'none', '', 'accepted'], ['f08', 'second_period', '10', 'thread', 'label_email', 'open', 'jun-ho gets a label email', '10', '', 'canon', 'audience', '10', 'junho:10', 'open', 'high', 'none', '', 'accepted'], ['f09', 'second_period', '10', 'thread', 'han_countermove', 'open', "han's quiet counter-move after exposure", '10', '', 'canon', 'audience', '10', 'han:10', 'open', 'high', 'none', '', 'accepted']]


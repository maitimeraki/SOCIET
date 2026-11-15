from src.simulation.evidence import MAX_ITEM_CHARS, ChunkRow, build_pack, sentence_spans

CHUNK = ChunkRow("c1", "d1", "Deal memo", "Acquisitions",
                 "Amazon acquired Whole Foods in 2017. The deal was valued at $13.7 billion. Weather was mild.", 0.9)


def test_own_items_name_the_entity():
    pack = build_pack("Whole Foods", [], [CHUNK], [])
    assert [i.text for i in pack.items] == ["Amazon acquired Whole Foods in 2017."]


def test_a_name_past_the_character_cap_still_owns_the_sentence():
    sentence = " ".join(["x" * 13] * 30) + " Kestra ships the pilot."
    pack = build_pack("Kestra", [], [ChunkRow("c1", "d1", "Memo", "Pricing", sentence, 0.9)], [])
    assert [len(i.text) for i in pack.items] == [MAX_ITEM_CHARS]


def test_every_item_resolves_to_exact_text():
    pack = build_pack("Whole Foods", [], [CHUNK], [])
    assert all(CHUNK.text[i.span[0]:i.span[1]] == i.text for i in pack.items)


def test_long_sentences_are_clipped_to_forty_words_and_still_resolve():
    long = ChunkRow("c2", "d1", "T", "", "Whole Foods " + "word " * 60 + "ends here.", 0.5)
    item = build_pack("Whole Foods", [], [long], []).items[0]
    assert len(item.text.split()) == 40 and long.text[item.span[0]:item.span[1]] == item.text


def test_an_alias_counts_as_naming_the_entity():
    assert build_pack("Whole Foods Market", ["WFM"], [ChunkRow("c3", "d", "T", "", "WFM opened a store.", 0.5)], []).items


def test_shared_chunk_gives_each_agent_only_its_own_sentences():
    shared = ChunkRow("c4", "d", "T", "", "Kestra raised prices. Orin cut prices.", 0.5)
    assert [i.text for i in build_pack("Kestra", [], [shared], []).items] == ["Kestra raised prices."]


def test_items_are_ranked_by_chunk_score_then_position_and_capped():
    chunks = [ChunkRow(f"c{n}", "d", "T", "", f"Kestra sentence {n}.", n / 100) for n in range(20)]
    pack = build_pack("Kestra", [], chunks, [])
    assert len(pack.items) == 12 and pack.items[0].chunk_id == "c19"


def test_documents_and_chunks_are_counted_from_the_items():
    pack = build_pack("Kestra", [], [ChunkRow("a", "d1", "T", "", "Kestra a.", 1), ChunkRow("b", "d2", "T", "", "Kestra b.", 1)], [])
    assert (pack.doc_count, pack.chunk_count) == (2, 2)


def test_a_name_beyond_word_forty_yields_no_item():
    late = ChunkRow("c5", "d", "T", "", "word " * 45 + "Kestra closes.", 0.5)
    assert build_pack("Kestra", [], [late], []).items == ()


def test_a_blank_name_yields_no_items():
    assert build_pack("  ", [], [CHUNK], []).items == ()


def test_blank_aliases_yield_no_items():
    assert build_pack("", ["  ", ""], [CHUNK], []).items == ()


def test_a_padded_name_still_matches():
    padded = ChunkRow("c6", "d", "T", "", "Kestra raised prices.", 0.5)
    assert [i.text for i in build_pack(" Kestra ", [], [padded], []).items] == ["Kestra raised prices."]


def test_leading_whitespace_is_trimmed_from_the_first_span():
    assert sentence_spans("  Kestra raised prices. Orin cut.")[0] == (2, 2 + len("Kestra raised prices."))


def test_leading_whitespace_is_not_part_of_an_item():
    lead = ChunkRow("c7", "d", "T", "", "  Kestra raised prices.", 0.5)
    assert build_pack("Kestra", [], [lead], []).items[0].text == "Kestra raised prices."


def test_a_real_name_with_a_blank_alias_still_matches_only_named_sentences():
    mixed = ChunkRow("c8", "d", "T", "", "Orin cut prices. Kestra raised.", 1)
    assert [i.text for i in build_pack("Kestra", ["  "], [mixed], []).items] == ["Kestra raised."]


def test_a_name_at_word_forty_is_owned():
    edge = ChunkRow("c9", "d", "T", "", "word " * 39 + "Kestra closes.", 0.5)
    assert [i.text for i in build_pack("Kestra", [], [edge], []).items] == ["word " * 39 + "Kestra"]


def test_a_name_at_word_forty_one_is_not_owned():
    past = ChunkRow("c10", "d", "T", "", "word " * 40 + "Kestra closes.", 0.5)
    assert build_pack("Kestra", [], [past], []).items == ()

from app.agent_core.addressing import AddressProfile, apply_llm_addressing, resolve_profile


def test_no_keyword_rule_infers_an_address_from_the_current_message():
    # The resolver deliberately does not parse "bác/cô/anh" anymore.
    assert resolve_profile().customer_addr == ""


def test_llm_can_use_terms_outside_a_fixed_dictionary():
    profile = apply_llm_addressing(AddressProfile(), {
        "customer_address": "thầy", "bot_self_term": "em", "addressing_confidence": "high",
    })
    assert (profile.customer_addr, profile.self_term, profile.source) == ("thầy", "em", "llm")


def test_explicit_customer_preference_is_recorded_as_such():
    profile = apply_llm_addressing(AddressProfile(), {
        "customer_address": "cô giáo", "bot_self_term": "em", "addressing_confidence": "high",
        "addressing_explicit": True,
    })
    assert (profile.customer_addr, profile.self_term, profile.confidence, profile.source) == (
        "cô giáo", "em", "explicit", "customer")


def test_low_confidence_llm_does_not_replace_a_session_profile():
    current = AddressProfile("bác", "cháu", "explicit", "customer")
    updated = apply_llm_addressing(current, {
        "customer_address": "anh", "bot_self_term": "em", "addressing_confidence": "unknown",
    })
    assert updated == current


def test_inference_cannot_override_an_explicit_session_preference():
    current = AddressProfile("bác", "cháu", "explicit", "customer")
    updated = apply_llm_addressing(current, {
        "customer_address": "anh", "bot_self_term": "em", "addressing_confidence": "high",
    })
    assert updated == current


def test_profile_persists_without_parsing_later_messages():
    profile = resolve_profile({
        "customer_addr": "cô", "bot_self_term": "cháu", "address_confidence": "explicit",
        "address_source": "customer",
    })
    assert profile == AddressProfile("cô", "cháu", "explicit", "customer")

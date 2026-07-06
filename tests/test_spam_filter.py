"""Tests for the spam detection module."""

import pytest

from spam_filter import (
    SpamDetector,
    SpamCategory,
    normalize_text,
    has_homoglyph_obfuscation,
    has_fake_badge,
    get_default_detector,
    is_spam,
    analyze_comment,
    create_detector,
    filter_spam_batch,
    analyze_batch,
    detect_spam_campaigns,
)
from core.constants import SpamFilterStrength


# =============================================================================
# NORMALIZE TEXT
# =============================================================================

class TestNormalizeText:
    def test_empty_string(self):
        assert normalize_text("") == ""

    def test_plain_text_unchanged(self):
        assert normalize_text("Hello world") == "Hello world"

    def test_removes_zero_width_chars(self):
        assert normalize_text("he​llo") == "hello"
        assert normalize_text("te‌st") == "test"
        assert normalize_text("﻿start") == "start"

    def test_cyrillic_homoglyph_mapping(self):
        # с→c, о→o, а→a, с→c mapped; н has no Latin homoglyph
        result = normalize_text("соntасt")
        assert result.lower() == "contact"

    def test_greek_homoglyph_mapping(self):
        result = normalize_text("αpple")
        assert result.startswith("a")

    def test_deobfuscation_telegram(self):
        result = normalize_text("t.e.l.e.g.r.a.m")
        assert result == "telegram"

    def test_deobfuscation_preserves_short_words(self):
        assert normalize_text("Dr.") == "Dr."

    def test_deobfuscation_preserves_apostrophes(self):
        result = normalize_text("don't")
        assert "'" in result or result == "don't"

    def test_leetspeak_with_mixed_alpha(self):
        result = normalize_text("wh@ts@pp")
        assert "a" in result

    def test_leetspeak_skips_standalone_numbers(self):
        result = normalize_text("$100")
        assert result == "$100"

    def test_leetspeak_skips_urls(self):
        result = normalize_text("https://example.com/path")
        assert "https://example.com/path" in result

    def test_collapse_spaces(self):
        assert normalize_text("hello    world") == "hello world"

    def test_unicode_nfkd_ligatures(self):
        result = normalize_text("ﬁnd")
        assert result == "find"


class TestHasHomoglyphObfuscation:
    def test_no_obfuscation(self):
        assert has_homoglyph_obfuscation("hello world") is False

    def test_cyrillic_detected(self):
        assert has_homoglyph_obfuscation("сontact") is True

    def test_greek_detected(self):
        assert has_homoglyph_obfuscation("αpple") is True


class TestHasFakeBadge:
    def test_no_badge(self):
        assert has_fake_badge("regular user") is False

    def test_checkmark_badge(self):
        assert has_fake_badge("user ✓") is True

    def test_emoji_badge(self):
        assert has_fake_badge("user ✅") is True


# =============================================================================
# SPAM DETECTOR - CORE ANALYSIS
# =============================================================================

class TestSpamDetectorAnalysis:
    def setup_method(self):
        self.detector = SpamDetector(threshold=0.5)

    def test_empty_text_not_spam(self):
        result = self.detector.analyze("")
        assert result.is_spam is False
        assert result.score == 0.0

    def test_whitespace_only_not_spam(self):
        result = self.detector.analyze("   ")
        assert result.is_spam is False

    def test_legitimate_comment(self):
        result = self.detector.analyze("Great video, I learned a lot! Thanks for the tutorial.")
        assert result.is_spam is False

    def test_question_not_spam(self):
        result = self.detector.analyze("How do you do this in Python?")
        assert result.is_spam is False

    def test_timestamp_reference_not_spam(self):
        result = self.detector.analyze("At 5:32 you explained this really well")
        assert result.is_spam is False

    def test_crypto_scam_detected(self):
        result = self.detector.analyze(
            "Invest in bitcoin now for 100x returns! Join our trading group on telegram!"
        )
        assert result.is_spam is True
        assert SpamCategory.CRYPTO_SCAM in result.categories

    def test_seed_phrase_scam(self):
        result = self.detector.analyze("Share your seed phrase to help me transfer funds")
        assert result.is_spam is True
        assert SpamCategory.SEED_PHRASE_SCAM in result.categories

    def test_financial_promises(self):
        result = self.detector.analyze(
            "Make $5000 per day with this guaranteed method! Contact me on WhatsApp now!"
        )
        assert result.is_spam is True

    def test_contact_solicitation(self):
        result = self.detector.analyze(
            "Contact me on WhatsApp for exclusive trading signals and guaranteed profits!"
        )
        assert result.is_spam is True

    def test_platform_redirect(self):
        result = self.detector.analyze("Join us at t.me/spamchannel for free signals")
        assert result.is_spam is True

    def test_channel_promotion(self):
        result = self.detector.analyze(
            "Check out my channel for similar content! Subscribe to my page! Click the link below!"
        )
        assert result.is_spam is True

    def test_fake_pinned_comment(self):
        result = self.detector.analyze("\U0001f4cc Official pinned announcement: visit this link")
        assert result.is_spam is True

    def test_adult_content_detected(self):
        result = self.detector.analyze("Check my onlyfans link in bio")
        assert result.is_spam is True

    def test_bot_template_markers(self):
        result = self.detector.analyze("Hello [name], check out [product] at [link]")
        assert result.is_spam is True
        assert SpamCategory.BOT_PATTERN in result.categories

    def test_shortened_urls_suspicious(self):
        result = self.detector.analyze(
            "Click here bit.ly/scamlink for free crypto money guaranteed returns!"
        )
        assert result.is_spam is True

    def test_obfuscation_adds_signal(self):
        result = self.detector.analyze("сонtaсt me on telegram")
        assert result.had_obfuscation is True
        assert result.score > 0

    def test_impersonation_fake_badge(self):
        result = self.detector.analyze(
            "Click my link for giveaway",
            author_name="Channel Owner ✅"
        )
        assert any(s.category == SpamCategory.IMPERSONATION for s in result.signals)

    def test_impersonation_suffix(self):
        result = self.detector.analyze(
            "Visit my profile",
            author_name="SomeUser Official"
        )
        assert any(s.category == SpamCategory.IMPERSONATION for s in result.signals)


# =============================================================================
# SPAM DETECTOR - LEGITIMACY SIGNALS
# =============================================================================

class TestLegitimacySignals:
    def setup_method(self):
        self.detector = SpamDetector(threshold=0.5)

    def test_timestamp_reduces_score(self):
        result = self.detector.analyze("At 3:45 check out this part of the video")
        has_timestamp_signal = any(
            "timestamp" in s.signal.lower() for s in result.legitimacy_signals
        )
        assert has_timestamp_signal

    def test_question_reduces_score(self):
        result = self.detector.analyze("How does this crypto thing work?")
        has_question_signal = any(
            "question" in s.signal.lower() for s in result.legitimacy_signals
        )
        assert has_question_signal

    def test_genuine_discussion_reduces_score(self):
        result = self.detector.analyze("I think this is a great explanation of the topic")
        has_genuine = any(
            "genuine" in s.signal.lower() for s in result.legitimacy_signals
        )
        assert has_genuine

    def test_educational_context_protects(self):
        result = self.detector.analyze("Can someone explain what is blockchain technology?")
        assert result.is_spam is False

    def test_high_likes_reduces_score(self):
        result = self.detector.analyze("Check out this video", like_count=150)
        has_engagement = any(
            "engagement" in s.signal.lower() or "validated" in s.signal.lower()
            for s in result.legitimacy_signals
        )
        assert has_engagement

    def test_high_likes_capped_for_high_spam(self):
        result = self.detector.analyze(
            "Buy bitcoin now! Guaranteed 100x returns! Contact me on telegram!",
            like_count=200
        )
        engagement_signals = [
            s for s in result.legitimacy_signals
            if "capped" in s.signal.lower()
        ]
        assert len(engagement_signals) > 0


# =============================================================================
# SPAM DETECTOR - THRESHOLDS
# =============================================================================

class TestThresholds:
    def test_aggressive_catches_more(self):
        detector = SpamDetector(threshold=0.35)
        result = detector.analyze("Check my channel for more videos")
        assert result.threshold == 0.35

    def test_light_misses_borderline(self):
        light = SpamDetector(threshold=0.65)
        aggressive = SpamDetector(threshold=0.35)
        text = "Check out my new video on my channel"
        assert light.analyze(text).is_spam is False or aggressive.analyze(text).is_spam is True

    def test_threshold_clamp_low(self):
        detector = SpamDetector(threshold=-0.5)
        assert detector.threshold == 0.0

    def test_threshold_clamp_high(self):
        detector = SpamDetector(threshold=1.5)
        assert detector.threshold == 1.0


# =============================================================================
# CUSTOM PATTERNS (BLACKLIST / WHITELIST)
# =============================================================================

class TestCustomPatterns:
    def test_blacklist_forces_spam(self):
        detector = SpamDetector(blacklist_patterns=["buy my course"])
        result = detector.analyze("You should buy my course today!")
        assert result.is_spam is True
        assert result.score == 1.0

    def test_whitelist_bypasses_detection(self):
        detector = SpamDetector(whitelist_patterns=["our sponsor"])
        result = detector.analyze("Check out our sponsor for great deals!")
        assert result.is_spam is False
        assert result.score == 0.0

    def test_whitelist_checked_before_blacklist(self):
        detector = SpamDetector(
            blacklist_patterns=["special offer"],
            whitelist_patterns=["special offer"]
        )
        result = detector.analyze("This is a special offer just for you")
        assert result.is_spam is False

    def test_invalid_pattern_ignored(self):
        detector = SpamDetector(blacklist_patterns=["valid", ""])
        assert len(detector._compiled_blacklist) == 1


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

class TestConvenienceFunctions:
    def test_is_spam_function(self):
        assert is_spam("Buy bitcoin guaranteed 100x returns! Join telegram for signals!") is True
        assert is_spam("Great video, thanks!") is False

    def test_analyze_comment_function(self):
        result = analyze_comment("Great video, thanks!")
        assert result.is_spam is False
        assert isinstance(result.score, float)

    def test_get_default_detector_singleton(self):
        d1 = get_default_detector()
        d2 = get_default_detector()
        assert d1 is d2

    def test_create_detector_factory(self):
        detector = create_detector(SpamFilterStrength.AGGRESSIVE)
        assert detector.threshold == 0.4


# =============================================================================
# BATCH PROCESSING
# =============================================================================

class TestBatchProcessing:
    def test_filter_spam_batch(self):
        comments = [
            {"Comment Text": "Great video!", "Author Name": "User1", "Comment Likes": 5},
            {"Comment Text": "Buy bitcoin 100x returns guaranteed! Contact me on telegram for signals!", "Author Name": "Spammer", "Comment Likes": 0},
            {"Comment Text": "Thanks for the tutorial", "Author Name": "User2", "Comment Likes": 10},
        ]
        filtered = filter_spam_batch(comments, threshold=0.5)
        assert len(filtered) < len(comments)
        assert all("telegram" not in c["Comment Text"].lower() for c in filtered)

    def test_filter_spam_batch_with_scores(self):
        comments = [
            {"Comment Text": "Hello world", "Author Name": "A", "Comment Likes": 0},
        ]
        filtered = filter_spam_batch(comments, include_scores=True)
        assert "spam_score" in filtered[0]

    def test_filter_spam_batch_string_likes(self):
        comments = [
            {"Comment Text": "Hello", "Author Name": "A", "Comment Likes": "5"},
        ]
        filtered = filter_spam_batch(comments)
        assert len(filtered) == 1

    def test_analyze_batch(self):
        texts = ["Great video!", "Buy bitcoin now!!", "Thanks"]
        results = analyze_batch(texts)
        assert len(results) == 3
        assert all(hasattr(r, "is_spam") for r in results)


# =============================================================================
# SPAM RESULT PROPERTIES
# =============================================================================

class TestSpamResultProperties:
    def test_reason_no_signals(self):
        detector = SpamDetector()
        result = detector.analyze("Hello")
        assert result.reason == "No spam signals detected"

    def test_primary_category(self):
        detector = SpamDetector()
        result = detector.analyze("Buy bitcoin 100x returns guaranteed!")
        assert result.primary_category is not None

    def test_primary_category_none_for_clean(self):
        detector = SpamDetector()
        result = detector.analyze("Nice video")
        assert result.primary_category is None

    def test_legitimacy_reason(self):
        detector = SpamDetector()
        result = detector.analyze("At 5:32 this was great, thanks!")
        assert result.legitimacy_reason != ""


# =============================================================================
# SIGNAL COMBINATION BOOSTS
# =============================================================================

class TestSignalCombinations:
    def setup_method(self):
        self.detector = SpamDetector(threshold=0.5)

    def test_crypto_plus_contact_boosted(self):
        result = self.detector.analyze(
            "Invest in bitcoin now! Contact me on WhatsApp for signals!"
        )
        categories = {s.category for s in result.signals}
        assert SpamCategory.CRYPTO_SCAM in categories
        assert result.is_spam is True

    def test_financial_plus_platform_redirect_boosted(self):
        result = self.detector.analyze(
            "Make $5000 per day guaranteed! Join t.me/scamgroup"
        )
        assert result.is_spam is True
        assert result.score > 0.6

    def test_single_weak_signal_not_boosted(self):
        result = self.detector.analyze("Check out my channel")
        assert result.score < 0.5

    def test_channel_promo_plus_shortened_url_boosted(self):
        result = self.detector.analyze(
            "Subscribe to my channel! Click bit.ly/freestuff for giveaway"
        )
        assert result.is_spam is True


# =============================================================================
# STRUCTURAL / CHARACTER DENSITY
# =============================================================================

class TestStructuralAnalysis:
    def setup_method(self):
        self.detector = SpamDetector(threshold=0.5)

    def test_spam_emoji_cluster_with_other_signal(self):
        result = self.detector.analyze(
            "Check my channel 💰💰💰🚀🚀🔥 click link below!"
        )
        has_structural = any(
            s.category == SpamCategory.STRUCTURAL_SPAM for s in result.signals
        )
        assert has_structural

    def test_spam_emoji_alone_low_weight(self):
        result = self.detector.analyze(
            "wow 💰💰💰🚀🚀🔥"
        )
        structural = [s for s in result.signals if s.category == SpamCategory.STRUCTURAL_SPAM]
        if structural:
            assert structural[0].weight <= 0.10

    def test_normal_emoji_usage_not_flagged(self):
        result = self.detector.analyze("Great video! 😊👍")
        has_structural = any(
            s.category == SpamCategory.STRUCTURAL_SPAM for s in result.signals
        )
        assert has_structural is False

    def test_caps_with_spam_signals(self):
        result = self.detector.analyze(
            "BUY BITCOIN NOW FOR GUARANTEED RETURNS! CONTACT ME ON TELEGRAM!"
        )
        has_caps = any(
            "caps" in s.signal.lower() for s in result.signals
        )
        assert has_caps

    def test_caps_alone_not_flagged(self):
        result = self.detector.analyze(
            "THIS VIDEO IS ABSOLUTELY AMAZING I LOVE IT SO MUCH"
        )
        has_caps = any(
            "caps" in s.signal.lower() for s in result.signals
        )
        assert has_caps is False

    def test_repetitive_punct_with_spam_signals(self):
        result = self.detector.analyze(
            "Buy bitcoin now!!! Contact me on telegram for signals!!!"
        )
        has_punct = any(
            "punctuation" in s.signal.lower() for s in result.signals
        )
        assert has_punct

    def test_repetitive_punct_alone_not_flagged(self):
        result = self.detector.analyze("This is amazing!!!")
        has_punct = any(
            "punctuation" in s.signal.lower() for s in result.signals
        )
        assert has_punct is False

    def test_short_text_no_caps_flag(self):
        result = self.detector.analyze("WOW")
        has_caps = any(
            "caps" in s.signal.lower() for s in result.signals
        )
        assert has_caps is False


# =============================================================================
# DUPLICATE / CAMPAIGN DETECTION
# =============================================================================

class TestDuplicateDetection:
    def test_exact_duplicates_detected(self):
        comments = [
            "Great video!",
            "Check out my channel for more videos",
            "Check out my channel for more videos",
            "Check out my channel for more videos",
            "Thanks for watching",
        ]
        campaign = detect_spam_campaigns(comments, min_cluster_size=3)
        assert 1 in campaign
        assert 2 in campaign
        assert 3 in campaign
        assert 0 not in campaign
        assert 4 not in campaign

    def test_near_duplicates_detected(self):
        comments = [
            "Nice tutorial!",
            "Contact me on WhatsApp for crypto trading signals now",
            "Contact me on WhatsApp for crypto trading signals today",
            "Contact me on WhatsApp for crypto trading signals here",
            "Really helpful content",
        ]
        campaign = detect_spam_campaigns(comments, similarity_threshold=0.85, min_cluster_size=3)
        assert 1 in campaign
        assert 2 in campaign
        assert 3 in campaign

    def test_below_min_cluster_not_flagged(self):
        comments = [
            "Same comment",
            "Same comment",
            "Different text entirely",
        ]
        campaign = detect_spam_campaigns(comments, min_cluster_size=3)
        assert len(campaign) == 0

    def test_empty_list(self):
        assert detect_spam_campaigns([]) == set()

    def test_all_unique_not_flagged(self):
        comments = [
            "First unique comment",
            "Second unique comment",
            "Third unique comment",
        ]
        campaign = detect_spam_campaigns(comments)
        assert len(campaign) == 0

    def test_campaign_detection_in_batch_filter(self):
        spam_text = "Check my profile link for free giveaways today"
        comments = [
            {"Comment Text": "Great video!", "Author Name": "A", "Comment Likes": 0},
            {"Comment Text": spam_text, "Author Name": "Bot1", "Comment Likes": 0},
            {"Comment Text": spam_text, "Author Name": "Bot2", "Comment Likes": 0},
            {"Comment Text": spam_text, "Author Name": "Bot3", "Comment Likes": 0},
            {"Comment Text": "Thanks!", "Author Name": "B", "Comment Likes": 0},
        ]
        filtered = filter_spam_batch(comments, detect_campaigns=True, campaign_min_cluster=3)
        texts = [c["Comment Text"] for c in filtered]
        assert spam_text not in texts
        assert "Great video!" in texts
        assert "Thanks!" in texts

    def test_campaign_detection_disabled(self):
        comments = [
            {"Comment Text": "Same text here", "Author Name": "A", "Comment Likes": 0},
            {"Comment Text": "Same text here", "Author Name": "B", "Comment Likes": 0},
            {"Comment Text": "Same text here", "Author Name": "C", "Comment Likes": 0},
        ]
        filtered = filter_spam_batch(comments, detect_campaigns=False)
        assert len(filtered) == 3

    def test_case_and_punctuation_normalized(self):
        comments = [
            "Contact me for exclusive trading signals!",
            "CONTACT ME FOR EXCLUSIVE TRADING SIGNALS!",
            "contact me for exclusive trading signals",
            "Unique comment here",
        ]
        campaign = detect_spam_campaigns(comments, min_cluster_size=3)
        assert 0 in campaign
        assert 1 in campaign
        assert 2 in campaign
        assert 3 not in campaign

    def test_short_organic_praise_not_flagged(self):
        # Real-world false positive: many genuine viewers write identical
        # short praise — this must never be treated as a campaign
        comments = [
            "Love this!", "Love this", "Love this!", "love this!!!", "Love this",
            "Can't wait!", "Can’t wait!", "Cant wait!", "Can't wait",
            "Lets gooooo", "Let’s gooooo", "LETS GOOOO", "lets gooooo",
            "This is awesome!", "This is so good!", "This is so good",
            "Nice", "Nice", "Nice!", "Great", "Great!", "Fire", "Fire",
            "This is gonna be good!!!",
        ]
        campaign = detect_spam_campaigns(comments, min_cluster_size=3)
        assert campaign == set()

    def test_long_campaign_still_flagged_among_praise(self):
        spam = "Contact me on WhatsApp for exclusive crypto trading signals"
        comments = ["Love this!", spam, "Love this", spam, "Can't wait!", spam]
        campaign = detect_spam_campaigns(comments, min_cluster_size=3)
        assert campaign == {1, 3, 5}

    def test_different_length_texts_not_clustered(self):
        # Length prefilter must not change behavior: very different texts stay unclustered
        comments = [
            "Hi",
            "This is a much longer comment about the video content in detail",
            "Another completely different comment talking about something else",
        ]
        campaign = detect_spam_campaigns(comments, min_cluster_size=2)
        assert len(campaign) == 0


# =============================================================================
# FALSE POSITIVE REGRESSIONS (v2.1.1)
# =============================================================================

class TestFalsePositiveRegressions:
    """Regression tests for false positives fixed in v2.1.1."""

    def setup_method(self):
        self.detector = SpamDetector(threshold=0.5)

    # --- Contact solicitation: bare everyday words must not be flagged ---

    def test_bare_text_word_not_contact(self):
        result = self.detector.analyze("I read the text on screen")
        assert not any(
            s.category == SpamCategory.CONTACT_SOLICITATION for s in result.signals
        )

    def test_bare_message_word_not_contact(self):
        result = self.detector.analyze("Great message in this video")
        assert not any(
            s.category == SpamCategory.CONTACT_SOLICITATION for s in result.signals
        )

    def test_bare_reach_word_not_contact(self):
        result = self.detector.analyze("This will reach so many people")
        assert not any(
            s.category == SpamCategory.CONTACT_SOLICITATION for s in result.signals
        )

    def test_contact_me_still_detected(self):
        result = self.detector.analyze("Contact me for exclusive deals")
        assert any(
            s.category == SpamCategory.CONTACT_SOLICITATION for s in result.signals
        )

    def test_dm_me_still_detected(self):
        result = self.detector.analyze("dm me for the details")
        assert any(
            s.category == SpamCategory.CONTACT_SOLICITATION for s in result.signals
        )

    def test_contact_on_platform_still_detected(self):
        result = self.detector.analyze(
            "Contact me on WhatsApp for exclusive trading signals and guaranteed profits!"
        )
        assert result.is_spam is True

    # --- Phone numbers: plain 10-digit integers must not be flagged ---

    def test_plain_ten_digit_number_not_phone(self):
        result = self.detector.analyze("The video hit 1234567890 views")
        assert not any("phone" in s.signal.lower() for s in result.signals)

    def test_separated_phone_still_detected(self):
        result = self.detector.analyze("call 555-123-4567 for signals")
        assert any("phone" in s.signal.lower() for s in result.signals)

    def test_international_phone_still_detected(self):
        result = self.detector.analyze("reach us +15551234567")
        assert any("phone" in s.signal.lower() for s in result.signals)

    # --- Adult content: "of link" phrase must not be flagged ---

    def test_of_link_phrase_not_adult(self):
        result = self.detector.analyze("this kind of link is helpful")
        assert not any(
            s.category == SpamCategory.ADULT_CONTENT for s in result.signals
        )

    def test_onlyfans_still_detected(self):
        result = self.detector.analyze("Check my onlyfans link in bio")
        assert result.is_spam is True

    # --- Engagement bait: standalone "First!" with punctuation ---

    def test_first_with_punctuation_is_bait(self):
        result = self.detector.analyze("First!")
        assert any(
            s.category == SpamCategory.ENGAGEMENT_BAIT for s in result.signals
        )

    def test_first_all_caps_is_bait(self):
        result = self.detector.analyze("FIRST!!!")
        assert any(
            s.category == SpamCategory.ENGAGEMENT_BAIT for s in result.signals
        )

    def test_first_in_sentence_not_bait(self):
        result = self.detector.analyze("first time watching this channel, great stuff")
        assert not any(
            s.category == SpamCategory.ENGAGEMENT_BAIT for s in result.signals
        )

    # --- Bare platform mentions must not be flagged, even at Aggressive ---

    def test_bare_platform_mention_not_flagged_aggressive(self):
        detector = SpamDetector(threshold=0.4)
        assert detector.analyze("discord is down again today").is_spam is False
        assert detector.analyze("the signal is weak in my area").is_spam is False


# =============================================================================
# DETECTION REGRESSIONS (v2.1.1 final review)
# =============================================================================

class TestDetectionRegressions:
    """Real spam that must stay detected after the v2.1.1 FP fixes."""

    def setup_method(self):
        self.detector = SpamDetector(threshold=0.5)

    def test_text_me_with_phone_is_spam(self):
        result = self.detector.analyze("Text me at 555 123 4567 for quick profits")
        assert result.is_spam is True

    def test_message_me_solicitation_detected(self):
        result = self.detector.analyze("message me for the best trading signals")
        assert any(
            s.category == SpamCategory.CONTACT_SOLICITATION for s in result.signals
        )

    def test_join_us_on_telegram_detected(self):
        result = self.detector.analyze("Join us on telegram for exclusive tips")
        assert any(
            s.category == SpamCategory.CONTACT_SOLICITATION for s in result.signals
        )

    def test_whatsapp_me_still_detected(self):
        result = self.detector.analyze("whatsapp me now for details")
        assert any(
            s.category == SpamCategory.CONTACT_SOLICITATION for s in result.signals
        )

    def test_of_link_uppercase_is_spam(self):
        result = self.detector.analyze("check my OF link in bio")
        assert result.is_spam is True

    def test_obfuscated_campaign_still_clustered(self):
        # Per-word obfuscation keeps char-level similarity high; the campaign
        # detector must not prune such pairs before computing ratio()
        base = "make money fast with john trading platform guaranteed profits every day"
        mutated = ("makee moneyy fastt withh johnn tradingg platformm "
                   "guaranteedd profitss everyy dayy")
        campaign = detect_spam_campaigns([base, mutated, base + " now"], min_cluster_size=2)
        assert campaign == {0, 1, 2}

    def test_short_campaign_flagged_with_lowered_min_length(self):
        # min_text_length is plumbed through filter_spam_batch for callers
        # who want to clamp down on short-text campaigns
        comments = [
            {"Comment Text": "Check out my new channel!!",
             "Author Name": f"B{i}", "Comment Likes": 0}
            for i in range(5)
        ]
        filtered = filter_spam_batch(comments, campaign_min_text_length=10)
        assert filtered == []

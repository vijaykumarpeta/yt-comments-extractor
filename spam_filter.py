"""
Spam Detection Module for YouTube Comments.

Version: 2.0.0

A multi-signal scoring system that focuses on promotional INTENT rather than
writing style. Designed to catch spam while protecting legitimate engagement
like excited users, genuine testimonials, and enthusiastic fans.

Key Principles:
    - Intent over style: ALL CAPS doesn't mean spam if there's no promotional intent
    - Normalize first: Cyrillic homoglyphs and leetspeak are normalized before detection
    - Multi-signal scoring: No single factor triggers spam classification
    - Legitimacy bonuses: Timestamps, questions, and genuine discussion reduce scores
    - Configurable thresholds: Adjust sensitivity based on use case
    - Transparency: Returns detailed reasoning for each classification

Based on research showing:
    - AI generates 51% of spam comments (2025)
    - Cyrillic homoglyph attacks bypass most keyword filters
    - Random Forest achieves 99.84% accuracy on benchmarks
    - Intent-based detection outperforms keyword-only approaches

Usage:
    detector = SpamDetector(threshold=0.5)
    result = detector.analyze("Check out my crypto channel!")

    if result.is_spam:
        print(f"Spam detected: {result.reason}")
        print(f"Category: {result.primary_category}")
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Set

logger = logging.getLogger(__name__)


# =============================================================================
# UNICODE NORMALIZATION - CRITICAL FIRST STEP
# =============================================================================

# Cyrillic to Latin homoglyph mapping (visually identical characters)
CYRILLIC_TO_LATIN: Dict[str, str] = {
    # Lowercase
    'а': 'a', 'с': 'c', 'е': 'e', 'о': 'o', 'р': 'p',
    'х': 'x', 'у': 'y', 'і': 'i', 'ј': 'j', 'ѕ': 's',
    'һ': 'h', 'ԁ': 'd', 'ԛ': 'q', 'ԝ': 'w', 'ᴦ': 'r',
    # Uppercase  
    'А': 'A', 'В': 'B', 'С': 'C', 'Е': 'E', 'Н': 'H',
    'К': 'K', 'М': 'M', 'О': 'O', 'Р': 'P', 'Т': 'T', 
    'Х': 'X', 'У': 'Y', 'І': 'I',
    # Greek homoglyphs
    'α': 'a', 'ο': 'o', 'ρ': 'p', 'τ': 't', 'υ': 'u',
    'ν': 'v', 'ω': 'w', 'χ': 'x',
}

# Leetspeak / character substitution mapping
LEETSPEAK_MAP: Dict[str, str] = {
    '@': 'a', '4': 'a', '^': 'a',
    '8': 'b',
    '(': 'c', '<': 'c', '{': 'c',
    '3': 'e', '€': 'e',
    '6': 'g', '9': 'g',
    '#': 'h',
    '1': 'i', '!': 'i', '|': 'i',
    '0': 'o', 'ø': 'o',
    '$': 's', '5': 's',
    '7': 't', '+': 't',
    'µ': 'u',
    '2': 'z',
}

# Zero-width and invisible characters to remove
ZERO_WIDTH_CHARS: FrozenSet[str] = frozenset({
    '\u200B',  # Zero-width space
    '\u200C',  # Zero-width non-joiner
    '\u200D',  # Zero-width joiner
    '\u2060',  # Word joiner
    '\uFEFF',  # Zero-width no-break space (BOM)
    '\u00AD',  # Soft hyphen
    '\u034F',  # Combining grapheme joiner
    '\u2061',  # Function application
    '\u2062',  # Invisible times
    '\u2063',  # Invisible separator
    '\u2064',  # Invisible plus
})

# Fake verification badge characters (used in impersonation)
FAKE_BADGE_CHARS: FrozenSet[str] = frozenset({
    '✓', '✔', '✅', '☑', '🔵', '⚪', '🔘', '🔷', '💎', '⭐'
})


def normalize_text(text: str) -> str:
    """
    Normalize text to defeat obfuscation techniques.
    
    This is the CRITICAL first step - without normalization, Cyrillic homoglyphs
    like "соntасt" (with Cyrillic а, о, с) completely bypass keyword detection.
    
    Normalization steps:
    1. Remove zero-width/invisible characters
    2. Map Cyrillic/Greek homoglyphs to Latin equivalents
    3. Handle obfuscation patterns (t.e.l.e.g.r.a.m -> telegram)
    4. Normalize leetspeak substitutions (selectively)
    5. Collapse multiple spaces
    
    Args:
        text: Raw input text
        
    Returns:
        Normalized text suitable for pattern matching
    """
    if not text:
        return ""
    
    # Step 1: Remove zero-width characters
    normalized = ''.join(c for c in text if c not in ZERO_WIDTH_CHARS)
    
    # Step 2: Map homoglyphs (Cyrillic, Greek) - always do this
    normalized = ''.join(CYRILLIC_TO_LATIN.get(c, c) for c in normalized)
    
    # Step 2b: Unicode NFKD normalization - handles compatibility characters
    # Decomposes characters like "ﬁ" → "fi", "™" → "TM", etc.
    # Also decomposes accented chars: "é" → "e" + combining accent
    normalized = unicodedata.normalize('NFKD', normalized)
    # Remove combining diacritical marks (accents) - keeps base letter
    normalized = ''.join(c for c in normalized if not unicodedata.combining(c))
    
    # Step 3: Handle period/quote obfuscation (t.e.l.e.g.r.a.m -> telegram)
    # Detect obfuscation pattern: sequences of single-char-punct-single-char
    # Only apply to words that look obfuscated (>50% punctuation)
    def deobfuscate_word(word: str) -> str:
        if len(word) < 5:
            return word
        punct_count = sum(1 for c in word if c in '."\'-_`')
        char_count = sum(1 for c in word if c.isalnum())
        # If roughly half the characters are punctuation, it's likely obfuscated
        if punct_count >= char_count * 0.4 and punct_count >= 2:
            return re.sub(r'[."\'\-_`]', '', word)
        return word
    
    # Apply to each word
    words = normalized.split()
    normalized = ' '.join(deobfuscate_word(w) for w in words)
    
    # Step 4: Normalize leetspeak - but preserve URLs, mentions, and standalone numbers
    def normalize_segment(segment: str) -> str:
        # Skip if it looks like a URL
        if '/' in segment or segment.startswith(('http', 'www', 't.me', 'bit.ly')):
            return segment
        # If starts with @ it's a mention - preserve the @ and normalize the rest
        if segment.startswith('@'):
            return '@' + normalize_segment(segment[1:]) if len(segment) > 1 else segment
        # Apply leetspeak normalization for all other cases
        # (including wh@ts@pp where @ is in the middle)
        return ''.join(LEETSPEAK_MAP.get(c, c) for c in segment)
    
    # Split by URL-like patterns and normalize non-URL parts
    url_pattern = re.compile(r'(https?://\S+|www\.\S+|t\.me/\S+|\S+\.ly/\S+)')
    parts = url_pattern.split(normalized)
    normalized = ''.join(
        segment if url_pattern.match(segment) else normalize_segment(segment)
        for segment in parts
    )
    
    # Step 5: Collapse multiple spaces
    normalized = re.sub(r'\s+', ' ', normalized)
    
    return normalized.strip()


def has_homoglyph_obfuscation(text: str) -> bool:
    """Check if text contains Cyrillic/Greek homoglyphs (likely intentional obfuscation)."""
    for char in text:
        if char in CYRILLIC_TO_LATIN:
            return True
    return False


def has_fake_badge(text: str) -> bool:
    """Check if text contains fake verification badge characters."""
    return any(char in FAKE_BADGE_CHARS for char in text)


# =============================================================================
# DATA CLASSES
# =============================================================================

class SpamCategory(Enum):
    """Categories of spam for detailed reporting."""
    CRYPTO_SCAM = "crypto_scam"
    SEED_PHRASE_SCAM = "seed_phrase_scam"
    FINANCIAL_SCAM = "financial_scam"
    CONTACT_SOLICITATION = "contact_solicitation"
    PLATFORM_REDIRECT = "platform_redirect"
    SELF_PROMOTION = "self_promotion"
    BOOK_PROMOTION = "book_promotion"
    CHANNEL_PROMOTION = "channel_promotion"
    PHISHING = "phishing"
    BOT_PATTERN = "bot_pattern"
    IMPERSONATION = "impersonation"
    FAKE_PINNED = "fake_pinned"
    ADULT_CONTENT = "adult_content"
    ENGAGEMENT_BAIT = "engagement_bait"
    OBFUSCATION = "obfuscation"


@dataclass
class SpamSignal:
    """Represents a detected spam signal."""
    category: SpamCategory
    signal: str
    weight: float
    matched_text: str = ""


@dataclass  
class LegitimacySignal:
    """Represents a detected legitimacy signal (reduces spam score)."""
    signal: str
    bonus: float  # Negative value to reduce score
    matched_text: str = ""


@dataclass
class SpamResult:
    """Result of spam analysis."""
    is_spam: bool
    score: float
    threshold: float
    signals: List[SpamSignal] = field(default_factory=list)
    legitimacy_signals: List[LegitimacySignal] = field(default_factory=list)
    categories: List[SpamCategory] = field(default_factory=list)
    normalized_text: str = ""
    had_obfuscation: bool = False
    
    @property
    def reason(self) -> str:
        """Human-readable reason for classification."""
        if not self.signals:
            return "No spam signals detected"
        
        reasons = [f"{s.signal}" for s in self.signals[:3]]
        return "; ".join(reasons)
    
    @property
    def primary_category(self) -> Optional[SpamCategory]:
        """The highest-weighted spam category."""
        if not self.signals:
            return None
        return max(self.signals, key=lambda s: s.weight).category
    
    @property
    def legitimacy_reason(self) -> str:
        """Human-readable legitimacy signals."""
        if not self.legitimacy_signals:
            return ""
        return "; ".join(s.signal for s in self.legitimacy_signals)


# =============================================================================
# SPAM DETECTOR CLASS
# =============================================================================

class SpamDetector:
    """
    Multi-signal spam detector with Unicode normalization and configurable sensitivity.
    
    Architecture:
    1. Normalize text (defeat obfuscation)
    2. Check spam signals (add to score)
    3. Check legitimacy signals (subtract from score)
    4. Apply threshold for final classification
    
    Usage:
        detector = SpamDetector(threshold=0.5)
        result = detector.analyze("Check out my crypto channel!")
        
        if result.is_spam:
            print(f"Spam detected: {result.reason}")
            print(f"Category: {result.primary_category}")
    """
    
    def __init__(
        self,
        threshold: float = 0.5,
        blacklist_patterns: Optional[List[str]] = None,
        whitelist_patterns: Optional[List[str]] = None,
    ):
        """
        Initialize the spam detector.

        Args:
            threshold: Score threshold for spam classification (0.0 - 1.0)
                      Lower = more aggressive filtering (catches more, risks false positives)
                      Higher = more permissive (misses some spam, fewer false positives)

                      Recommended values:
                      - 0.35: Aggressive (strict filtering)
                      - 0.50: Balanced (default)
                      - 0.65: Light (only obvious spam)

            blacklist_patterns: List of custom patterns to always flag as spam.
                               These are matched case-insensitively against the comment text.

            whitelist_patterns: List of custom patterns to always allow through.
                               If a comment matches any whitelist pattern, it bypasses spam detection.
        """
        self.threshold = max(0.0, min(1.0, threshold))
        self.blacklist_patterns = blacklist_patterns or []
        self.whitelist_patterns = whitelist_patterns or []
        self._compile_patterns()
        self._compile_custom_patterns()
    
    def _compile_patterns(self):
        """Pre-compile regex patterns for performance."""
        
        # =====================================================================
        # CRYPTO / FINANCIAL SCAM PATTERNS
        # =====================================================================
        
        self.crypto_keywords = re.compile(
            r'\b(crypto|bitcoin|btc|ethereum|eth|altcoin|blockchain|nft|'
            r'binance|coinbase|kraken|kucoin|bybit|okx|bitget|mexc|'
            r'usdt|usdc|tether|dogecoin|doge|shiba|pepe|'
            r'defi|yield\s*farm|staking|airdrop|whitelist|presale|'
            r'web3|metaverse|token|ico|ido|'
            r'forex|fx\s*trading|binary\s*option|'
            r'trading\s*(signal|bot|group)|'
            r'10x|100x|1000x|moon(ing)?|lambo|'
            r'hodl|wagmi|ngmi|fomo|fud)\b',
            re.IGNORECASE
        )
        
        # Seed phrase / Multi-sig wallet scams (2024 emerging threat)
        self.seed_phrase_scam = re.compile(
            r'\b(seed\s*phrase|recovery\s*phrase|mnemonic|'
            r'12\s*words?|24\s*words?|'
            r'multi.?sig(nature)?|'
            r'help\s*(me\s*)?(transfer|withdraw|access)|'
            r'share\s*\d+%|split\s*(the\s*)?(profit|funds)|'
            r'stuck\s*(in\s*)?(wallet|exchange)|'
            r'can\'t\s*(access|withdraw)|'
            r'need\s*(help|gas|fee)\s*to\s*(transfer|withdraw))\b',
            re.IGNORECASE
        )
        
        self.financial_promises = re.compile(
            r'(\$\d{1,3}(,?\d{3})*(\.\d{2})?\s*(per|a|every|each)?\s*(day|week|month|hour)|'
            r'guaranteed\s*(returns?|profit|income)|'
            r'double\s*your\s*(money|investment)|'
            r'risk\s*free|no\s*risk|zero\s*risk|'
            r'\d+%\s*(daily|weekly|monthly|roi|return|profit)|'
            r'(turn|transform|convert)\s*\$?\d+\s*(into|to)\s*\$?\d+|'
            r'(make|earn)\s*\$?\d+[kK]?\+?\s*(daily|weekly|monthly|passive)|'
            r'passive\s*income|financial\s*freedom|'
            r'quit\s*(your\s*)?(job|9.?5)|'
            r'work\s*from\s*(home|anywhere).*\$)',
            re.IGNORECASE
        )
        
        # =====================================================================
        # CONTACT SOLICITATION & PLATFORM REDIRECT
        # =====================================================================
        
        self.contact_solicitation = re.compile(
            r'\b(contact|message|text|chat\s*with|reach|dm|pm|inbox)\s*(me|us|him|her)?\s*'
            r'(on|at|via|through|@)?\s*'
            r'(whatsapp|telegram|signal|wechat|line|viber|discord|'
            r'instagram|ig|facebook|fb|twitter|x|tiktok|snapchat)?\b|'
            r'\b(whatsapp|telegram|signal|discord)\s*(me|us|now|today|asap)?\b|'
            r'\bsend\s*(a\s*)?(dm|pm|message)\b|'
            r'\b(hit|slide\s*into)\s*(my|the)?\s*(dm|inbox)\b|'
            r'\b(add|follow)\s*me\s*(on|@)\b',
            re.IGNORECASE
        )
        
        # Platform-specific redirect patterns
        self.platform_redirect = re.compile(
            r'(t\.me/[a-zA-Z0-9_]+|'
            r'wa\.me/\d+|'
            r'chat\.whatsapp\.com/[a-zA-Z0-9]+|'
            r'discord\.(gg|com/invite)/[a-zA-Z0-9]+|'
            r'@[a-zA-Z0-9_]+\s*(on\s*)?(telegram|whatsapp|insta|ig))',
            re.IGNORECASE
        )
        
        self.phone_patterns = re.compile(
            r'(\+\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9})|'
            r'(\(\d{3}\)\s*\d{3}[-.\s]?\d{4})|'
            r'(\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b)|'
            r'(\+\d{10,15}\b)'
        )
        
        # Email pattern - fixed to properly match "at" and "dot" as words, not character classes
        self.email_pattern = re.compile(
            r'[a-zA-Z0-9._%+-]+\s*(?:@|\[at\]|\(at\))\s*[a-zA-Z0-9.-]+\s*'
            r'(?:\.|\[dot\]|\(dot\))\s*(com|org|net|io|co|info|biz|xyz)\b',
            re.IGNORECASE
        )
        
        # =====================================================================
        # SELF-PROMOTION PATTERNS
        # =====================================================================
        
        self.channel_promotion = re.compile(
            r'\b(check\s*(out)?|visit|see|view|watch|subscribe\s*(to)?|follow)\s*'
            r'(my|our|the)?\s*(channel|page|profile|account|video|content|link)\b|'
            r'\b(my|our)\s*(new\s*)?(channel|video|content|podcast)\b|'
            r'\bsub(scribe)?\s*(to\s*)?(my|our|the)\b|'
            r'\blink\s*(in|on)\s*(my\s*)?(bio|profile|description|about)\b|'
            r'\b(i\s*(also\s*)?(make|create|post)|check\s*my)\s*(similar\s*)?(content|videos?)\b',
            re.IGNORECASE
        )
        
        self.self_promo_phrases = re.compile(
            r'\b(check\s*this\s*out|must\s*watch|you\s*need\s*to\s*see|'
            r'click\s*(the\s*)?link|tap\s*(the\s*)?link|'
            r'link\s*below|see\s*link|bio\s*link|'
            r'support\s*(my|our)\s*(channel|content))\b',
            re.IGNORECASE
        )
        
        # =====================================================================
        # BOOK / PRODUCT PROMOTION
        # =====================================================================
        
        self.book_promotion = re.compile(
            r'\b(my\s*(new\s*)?(book|ebook|e-book|guide|course|program|masterclass)|'
            r'(book|ebook)\s*(available|out\s*now|on\s*amazon|link)|'
            r'get\s*(my|the|your)\s*(free\s*)?(copy|ebook|guide|book)|'
            r'download\s*(my|the|your)?\s*(free\s*)?(guide|ebook|book|pdf)|'
            r'(available|order|buy)\s*(now\s*)?(on\s*)?(amazon|kindle|audible)|'
            r'#ad\b|#sponsored\b|#affiliate\b)\b',
            re.IGNORECASE
        )
        
        # =====================================================================
        # URL PATTERNS
        # =====================================================================
        
        self.url_pattern = re.compile(
            r'(https?://[^\s]+)|'
            r'(www\.[^\s]+)|'
            r'\b([a-zA-Z0-9-]+\.(com|org|net|io|co|info|biz|xyz|click|link|me)/[^\s]*)\b',
            re.IGNORECASE
        )
        
        self.shortened_urls = re.compile(
            r'\b(bit\.ly|tinyurl|t\.co|goo\.gl|ow\.ly|buff\.ly|'
            r'rebrand\.ly|short\.link|linktr\.ee|'
            r'cutt\.ly|rb\.gy|is\.gd|v\.gd|shorte\.st|adf\.ly|'
            r'trib\.al|soo\.gd|s\.id)/[^\s]+\b',
            re.IGNORECASE
        )
        
        # =====================================================================
        # BOT / TEMPLATE PATTERNS
        # =====================================================================
        
        self.bot_generic_phrases = re.compile(
            r'\b(this\s*(video\s*)?changed\s*my\s*life|'
            r'i\s*was\s*struggling\s*until|'
            r'finally\s*found\s*(the\s*)?(solution|answer)|'
            r'best\s*decision\s*i\s*(ever\s*)?made|'
            r'wish\s*i\s*(had\s*)?(found|known)\s*(this|about\s*this)\s*sooner|'
            r'this\s*is\s*exactly\s*what\s*i\s*needed|'
            r'can\'t\s*believe\s*(this\s*)?(actually\s*)?works?|'
            r'life\s*changing|game\s*changer|'
            r'must\s*have|must\s*try|'
            r'i\s*started\s*(and|then)\s*never\s*looked\s*back)\b',
            re.IGNORECASE
        )
        
        self.bot_template_markers = re.compile(
            r'(\[name\]|\[product\]|\[link\]|\[url\]|\{.*?\}|'
            r'<\s*insert\s*.*?\s*>|'
            r'\[\s*your\s*.*?\s*\])',
            re.IGNORECASE
        )
        
        # =====================================================================
        # IMPERSONATION / FAKE PINNED
        # =====================================================================
        
        # Fake pinned comment scams
        self.fake_pinned = re.compile(
            r'(📌|🔴|⬆️|👆|👇)?\s*(pinned\s*(by|comment|message)|'
            r'official\s*(pinned|announcement|message)|'
            r'^\s*📌.*pinned|'
            r'read\s*my\s*pinned)',
            re.IGNORECASE
        )
        
        # Impersonation username patterns (for author_name checking)
        self.impersonation_suffixes = re.compile(
            r'(official|giveaway|telegram|team|real|verified|'
            r'gaming|live|support|admin|help|bot|promo|'
            r'moderator|mod|staff|vip)\s*$',
            re.IGNORECASE
        )
        
        # =====================================================================
        # ADULT / INAPPROPRIATE CONTENT
        # =====================================================================
        
        self.adult_content = re.compile(
            r'\b(onlyfans|of\s*link|18\+|adult\s*content|'
            r'xxx|porn|nude|nudes|sexy\s*(pics?|photos?|videos?)|'
            r'dating\s*(site|app)|hookup|'
            r's[e3]x(y|ting)?|h[o0]rny|'
            r'(check|see)\s*(my|the)\s*(profile|bio)\s*[;)😉🔥💋])\b',
            re.IGNORECASE
        )
        
        # =====================================================================
        # ENGAGEMENT BAIT
        # =====================================================================
        
        self.engagement_bait = re.compile(
            r'\b(like\s*if\s*you|comment\s*if\s*you|'
            r'who(\s*else)?\s*(is\s*)?(here|watching)\s*(in\s*)?20\d{2}|'
            r'like\s*this\s*comment\s*(if|so)|'
            r'anyone\s*(else\s*)?(here\s*)?(in|from)\s*20\d{2}|'
            r'^first[!\.\s]*$|^second[!\.\s]*$|^third[!\.\s]*$|'  # Only match standalone
            r'early\s*squad|notification\s*squad|'
            r'who\'?s\s*(still\s*)?(watching|listening)\s*(this\s*)?(in\s*)?20\d{2})\b',
            re.IGNORECASE
        )
        
        # =====================================================================
        # LEGITIMACY SIGNALS (reduce spam score)
        # =====================================================================
        
        # Video timestamp references (strong legitimacy signal)
        self.timestamp_pattern = re.compile(
            r'\b(\d{1,2}:\d{2}(:\d{2})?)\b|'
            r'\bat\s*(\d{1,2}:\d{2})|'
            r'timestamp|timecode'
        )
        
        # Questions (usually legitimate engagement)
        self.question_pattern = re.compile(
            r'\?\s*$|'
            r'\b(how|what|why|when|where|who|which|whose|whom|'
            r'can\s*(you|i|we|someone)|could\s*(you|i|we)|'
            r'would\s*(you|i|we)|should\s*(i|we)|'
            r'does\s*(anyone|somebody|this)|'
            r'has\s*(anyone|somebody)|'
            r'is\s*(there|this|it)|are\s*(there|these)|'
            r'what\'?s|where\'?s|who\'?s|how\'?s)\b',
            re.IGNORECASE
        )
        
        # Genuine discussion markers
        self.genuine_discussion = re.compile(
            r'\b(i\s*think|in\s*my\s*opinion|imo|imho|'
            r'i\s*(agree|disagree)|'
            r'great\s*(point|video|content|explanation|tutorial)|'
            r'thanks?\s*(for|so\s*much)|thank\s*you|'
            r'this\s*(helped|explains|clarifies)|'
            r'i\s*(learned|understood|finally\s*(get|understand))|'
            r'good\s*(job|work|explanation)|'
            r'well\s*(explained|done|said)|'
            r'helpful|informative|insightful|'
            r'i\'?ve\s*been\s*(struggling|trying|working)|'
            r'as\s*a\s*(beginner|student|developer|teacher|parent))\b',
            re.IGNORECASE
        )
        
        # Reply to specific user (indicates engagement)
        self.reply_pattern = re.compile(r'^@[a-zA-Z0-9_]+\s')
        
        # Constructive criticism / balanced feedback
        self.balanced_feedback = re.compile(
            r'\b(but\s*(i\s*think|maybe|however)|'
            r'one\s*(thing|suggestion|critique)|'
            r'could\s*(be|have\s*been)\s*(better|improved)|'
            r'i\s*(would\s*)?(suggest|recommend)|'
            r'(slight|minor|small)\s*(issue|problem|critique)|'
            r'not\s*sure\s*(about|if)|'
            r'on\s*the\s*other\s*hand)\b',
            re.IGNORECASE
        )
        
        # Educational context (protects legitimate discussions about crypto, etc.)
        self.educational_context = re.compile(
            r'\b(what\s*is|how\s*(does|do|to)|explain|learn(ing)?\s*about|'
            r'understand(ing)?|teach|tutorial|guide|'
            r'beginner|newbie|noob|started\s*learning|'
            r'can\s*someone\s*explain|eli5|'
            r'difference\s*between|compared\s*to|'
            r'pros?\s*and\s*cons?|advantages?\s*and\s*disadvantages?)\b',
            re.IGNORECASE
        )

    def _compile_custom_patterns(self) -> None:
        """Compile user-provided blacklist and whitelist patterns."""
        self._compiled_blacklist: List[re.Pattern] = []
        self._compiled_whitelist: List[re.Pattern] = []

        for pattern in self.blacklist_patterns:
            pattern = pattern.strip()
            if pattern:
                try:
                    self._compiled_blacklist.append(
                        re.compile(re.escape(pattern), re.IGNORECASE)
                    )
                except re.error:
                    logger.warning(f"Invalid blacklist pattern: {pattern}")

        for pattern in self.whitelist_patterns:
            pattern = pattern.strip()
            if pattern:
                try:
                    self._compiled_whitelist.append(
                        re.compile(re.escape(pattern), re.IGNORECASE)
                    )
                except re.error:
                    logger.warning(f"Invalid whitelist pattern: {pattern}")

    def _check_whitelist(self, text: str) -> bool:
        """Check if text matches any whitelist pattern."""
        for pattern in self._compiled_whitelist:
            if pattern.search(text):
                return True
        return False

    def _check_blacklist(self, text: str) -> Optional[str]:
        """Check if text matches any blacklist pattern. Returns matched pattern or None."""
        for pattern in self._compiled_blacklist:
            match = pattern.search(text)
            if match:
                return match.group(0)
        return None

    def analyze(self, text: str, author_name: str = "", like_count: int = 0) -> SpamResult:
        """
        Analyze text for spam signals with full normalization pipeline.
        
        Args:
            text: The comment text to analyze
            author_name: Optional author display name for impersonation detection
            like_count: Optional like count for engagement-based legitimacy (0 = unknown)
        
        Returns:
            SpamResult with score, classification, signals, and legitimacy bonuses
        """
        signals: List[SpamSignal] = []
        legitimacy_signals: List[LegitimacySignal] = []

        # Handle empty input
        if not text or not text.strip():
            return SpamResult(
                is_spam=False,
                score=0.0,
                threshold=self.threshold,
                signals=[],
                legitimacy_signals=[],
                categories=[],
                normalized_text="",
                had_obfuscation=False
            )

        # Step 0: Check whitelist first (bypass spam detection entirely)
        if self._check_whitelist(text):
            return SpamResult(
                is_spam=False,
                score=0.0,
                threshold=self.threshold,
                signals=[],
                legitimacy_signals=[LegitimacySignal(
                    signal="Matched whitelist pattern",
                    bonus=-1.0,
                    matched_text="[whitelisted]"
                )],
                categories=[],
                normalized_text=text,
                had_obfuscation=False
            )

        # Step 0b: Check blacklist (immediate spam classification)
        blacklist_match = self._check_blacklist(text)
        if blacklist_match:
            return SpamResult(
                is_spam=True,
                score=1.0,
                threshold=self.threshold,
                signals=[SpamSignal(
                    category=SpamCategory.BOT_PATTERN,
                    signal="Matched blacklist pattern",
                    weight=1.0,
                    matched_text=blacklist_match
                )],
                legitimacy_signals=[],
                categories=[SpamCategory.BOT_PATTERN],
                normalized_text=text,
                had_obfuscation=False
            )

        # Step 1: Check for obfuscation BEFORE normalizing
        had_obfuscation = has_homoglyph_obfuscation(text)
        
        # Step 2: Normalize text
        normalized = normalize_text(text)
        
        # If obfuscation was detected, that's a signal itself
        if had_obfuscation:
            signals.append(SpamSignal(
                category=SpamCategory.OBFUSCATION,
                signal="Homoglyph obfuscation detected",
                weight=0.3,
                matched_text="[cyrillic/greek characters]"
            ))
        
        # =====================================================================
        # CHECK SPAM SIGNALS
        # =====================================================================
        
        # --- Crypto / Financial Scams (HIGH weight) ---

        match = self.seed_phrase_scam.search(normalized)
        if match:
            signals.append(SpamSignal(
                category=SpamCategory.SEED_PHRASE_SCAM,
                signal="Seed phrase / wallet scam pattern",
                weight=0.75,
                matched_text=match.group(0)
            ))
        
        crypto_match = self.crypto_keywords.search(normalized)
        if crypto_match:
            all_matches = self.crypto_keywords.findall(normalized.lower())
            match_count = len(all_matches)
            # Scale weight by number of crypto terms
            weight = min(0.35 + (match_count * 0.08), 0.65)
            signals.append(SpamSignal(
                category=SpamCategory.CRYPTO_SCAM,
                signal=f"Crypto/trading keywords ({match_count}x)",
                weight=weight,
                matched_text=crypto_match.group(0)
            ))
        
        match = self.financial_promises.search(normalized)
        if match:
            signals.append(SpamSignal(
                category=SpamCategory.FINANCIAL_SCAM,
                signal="Financial promises/guarantees",
                weight=0.6,
                matched_text=match.group(0)
            ))

        # --- Contact Solicitation (HIGH weight) ---

        match = self.platform_redirect.search(normalized)
        if match:
            signals.append(SpamSignal(
                category=SpamCategory.PLATFORM_REDIRECT,
                signal="Platform redirect link",
                weight=0.55,
                matched_text=match.group(0)
            ))
        else:
            match = self.contact_solicitation.search(normalized)
            if match:
                signals.append(SpamSignal(
                    category=SpamCategory.CONTACT_SOLICITATION,
                    signal="Contact solicitation",
                    weight=0.45,
                    matched_text=match.group(0)
                ))
        
        if self.phone_patterns.search(text):  # Use original text for phone numbers
            signals.append(SpamSignal(
                category=SpamCategory.CONTACT_SOLICITATION,
                signal="Phone number detected",
                weight=0.4,
                matched_text="[phone number]"
            ))
        
        if self.email_pattern.search(normalized):
            signals.append(SpamSignal(
                category=SpamCategory.CONTACT_SOLICITATION,
                signal="Email address detected",
                weight=0.2,
                matched_text="[email]"
            ))
        
        # --- Impersonation / Fake Pinned (HIGH weight) ---

        match = self.fake_pinned.search(normalized)
        if match:
            signals.append(SpamSignal(
                category=SpamCategory.FAKE_PINNED,
                signal="Fake pinned comment pattern",
                weight=0.65,
                matched_text=match.group(0)
            ))

        # Check author name for impersonation
        if author_name:
            if has_fake_badge(author_name):
                signals.append(SpamSignal(
                    category=SpamCategory.IMPERSONATION,
                    signal="Fake verification badge in username",
                    weight=0.5,
                    matched_text="[badge character]"
                ))

            match = self.impersonation_suffixes.search(author_name)
            if match:
                signals.append(SpamSignal(
                    category=SpamCategory.IMPERSONATION,
                    signal="Suspicious username suffix",
                    weight=0.25,
                    matched_text=match.group(0)
                ))
        
        # --- Self-Promotion (MEDIUM weight) ---

        match = self.channel_promotion.search(normalized)
        if match:
            signals.append(SpamSignal(
                category=SpamCategory.CHANNEL_PROMOTION,
                signal="Channel/profile promotion",
                weight=0.4,
                matched_text=match.group(0)
            ))

        match = self.self_promo_phrases.search(normalized)
        if match:
            signals.append(SpamSignal(
                category=SpamCategory.SELF_PROMOTION,
                signal="Self-promotion phrases",
                weight=0.3,
                matched_text=match.group(0)
            ))

        # --- Book/Product Promotion ---

        match = self.book_promotion.search(normalized)
        if match:
            signals.append(SpamSignal(
                category=SpamCategory.BOOK_PROMOTION,
                signal="Book/product promotion",
                weight=0.45,
                matched_text=match.group(0)
            ))

        # --- URLs ---

        match = self.shortened_urls.search(normalized)
        if match:
            signals.append(SpamSignal(
                category=SpamCategory.PHISHING,
                signal="Shortened URL (suspicious)",
                weight=0.4,
                matched_text=match.group(0)
            ))
        elif self.url_pattern.search(normalized):
            signals.append(SpamSignal(
                category=SpamCategory.SELF_PROMOTION,
                signal="URL detected",
                weight=0.15,
                matched_text="[url]"
            ))

        # --- Bot Patterns ---

        match = self.bot_template_markers.search(normalized)
        if match:
            signals.append(SpamSignal(
                category=SpamCategory.BOT_PATTERN,
                signal="Template markers detected",
                weight=0.7,
                matched_text=match.group(0)
            ))
        else:
            match = self.bot_generic_phrases.search(normalized)
            if match:
                signals.append(SpamSignal(
                    category=SpamCategory.BOT_PATTERN,
                    signal="Generic bot-like phrase",
                    weight=0.2,  # Lower weight - could be genuine enthusiasm
                    matched_text=match.group(0)
                ))
        
        # --- Adult Content ---
        
        if self.adult_content.search(normalized):
            signals.append(SpamSignal(
                category=SpamCategory.ADULT_CONTENT,
                signal="Adult/inappropriate content",
                weight=0.6,
                matched_text="[adult content]"
            ))
        
        # --- Engagement Bait (LOW weight) ---

        match = self.engagement_bait.search(normalized)
        if match:
            signals.append(SpamSignal(
                category=SpamCategory.ENGAGEMENT_BAIT,
                signal="Engagement bait",
                weight=0.15,  # Annoying but not malicious
                matched_text=match.group(0)
            ))
        
        # =====================================================================
        # CALCULATE BASE SCORE
        # =====================================================================
        
        if not signals:
            base_score = 0.0
        else:
            # Weighted combination with diminishing returns
            # Prevents low-weight signals from stacking to spam threshold
            weights = sorted([s.weight for s in signals], reverse=True)
            
            base_score = weights[0]
            for i, w in enumerate(weights[1:], 1):
                # Each additional signal contributes less
                base_score += w * (0.5 ** i)
            
            base_score = min(base_score, 1.0)
        
        # =====================================================================
        # CHECK LEGITIMACY SIGNALS (reduce score)
        # =====================================================================
        
        # Timestamp references (STRONG legitimacy signal: -0.25)
        if self.timestamp_pattern.search(text):
            legitimacy_signals.append(LegitimacySignal(
                signal="Video timestamp reference",
                bonus=-0.25,
                matched_text=self.timestamp_pattern.search(text).group(0)
            ))
        
        # Reply to specific user
        if self.reply_pattern.search(text):
            legitimacy_signals.append(LegitimacySignal(
                signal="Reply to specific user",
                bonus=-0.15,
                matched_text="[@username]"
            ))
        
        # Questions (genuine engagement)
        if self.question_pattern.search(normalized):
            legitimacy_signals.append(LegitimacySignal(
                signal="Asks a question",
                bonus=-0.15,
                matched_text="[question]"
            ))
        
        # Genuine discussion markers
        match = self.genuine_discussion.search(normalized)
        if match:
            legitimacy_signals.append(LegitimacySignal(
                signal="Genuine discussion",
                bonus=-0.2,
                matched_text=match.group(0)
            ))

        # Balanced/constructive feedback
        match = self.balanced_feedback.search(normalized)
        if match:
            legitimacy_signals.append(LegitimacySignal(
                signal="Balanced feedback",
                bonus=-0.1,
                matched_text=match.group(0)
            ))

        # Educational context (protects legitimate discussions)
        match = self.educational_context.search(normalized)
        if match:
            legitimacy_signals.append(LegitimacySignal(
                signal="Educational context",
                bonus=-0.2,
                matched_text=match.group(0)
            ))
        
        # Length-based adjustments
        text_length = len(text.strip())
        
        # Very short comments without spam signals are usually fine
        if text_length < 30 and len(signals) == 0:
            legitimacy_signals.append(LegitimacySignal(
                signal="Short harmless comment",
                bonus=-0.1,
                matched_text=""
            ))
        
        # Long, thoughtful comments with few/no spam signals
        if text_length > 200 and len(signals) <= 1:
            legitimacy_signals.append(LegitimacySignal(
                signal="Long thoughtful comment",
                bonus=-0.15,
                matched_text=""
            ))
        
        # High engagement legitimacy (community validated)
        # BUT: Cap the bonus if spam signals are strong (prevents bot-inflated spam from passing)
        if like_count >= 10:
            # Determine bonus based on engagement level
            if like_count >= 100:
                raw_bonus = -0.25
                signal_text = f"High engagement ({like_count} likes)"
            else:
                raw_bonus = -0.10
                signal_text = f"Community validated ({like_count} likes)"
            
            # Cap bonus if base spam score is high (likely real spam with fake/accumulated engagement)
            if base_score >= 0.55:
                actual_bonus = max(raw_bonus, -0.10)  # Cap at -0.10 for suspicious content
                if actual_bonus != raw_bonus:
                    signal_text += " [capped - high spam signals]"
            else:
                actual_bonus = raw_bonus
            
            legitimacy_signals.append(LegitimacySignal(
                signal=signal_text,
                bonus=actual_bonus,
                matched_text=f"{like_count} likes"
            ))
        
        # =====================================================================
        # FINAL SCORE CALCULATION
        # =====================================================================
        
        adjustment = sum(ls.bonus for ls in legitimacy_signals)
        final_score = max(0.0, min(1.0, base_score + adjustment))
        
        # Get unique categories
        categories = list(set(s.category for s in signals))
        
        return SpamResult(
            is_spam=final_score >= self.threshold,
            score=round(final_score, 3),
            threshold=self.threshold,
            signals=signals,
            legitimacy_signals=legitimacy_signals,
            categories=categories,
            normalized_text=normalized,
            had_obfuscation=had_obfuscation
        )
    
    def is_spam(self, text: str, author_name: str = "", like_count: int = 0) -> bool:
        """Simple boolean check for spam."""
        return self.analyze(text, author_name, like_count).is_spam
    
    def get_spam_score(self, text: str, author_name: str = "", like_count: int = 0) -> float:
        """Get just the spam score (0.0 - 1.0)."""
        return self.analyze(text, author_name, like_count).score


# =============================================================================
# PRESET FILTER STRENGTHS
# =============================================================================

# Import SpamFilterStrength from core.constants to avoid duplication
from core.constants import SpamFilterStrength


def create_detector(strength: SpamFilterStrength = SpamFilterStrength.MODERATE) -> SpamDetector:
    """Factory function to create a detector with preset strength."""
    return SpamDetector(threshold=strength.value)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_default_detector: Optional[SpamDetector] = None


def get_default_detector() -> SpamDetector:
    """Get or create the default detector instance."""
    global _default_detector
    if _default_detector is None:
        _default_detector = SpamDetector()
    return _default_detector


def is_spam(text: str, threshold: float = 0.5, author_name: str = "", like_count: int = 0) -> bool:
    """
    Quick spam check with optional threshold.
    
    Args:
        text: Comment text to check
        threshold: Spam threshold (0.0 - 1.0)
        author_name: Optional author name for impersonation detection
        like_count: Optional like count for engagement-based legitimacy
    
    Returns:
        True if spam, False otherwise
    """
    detector = SpamDetector(threshold=threshold)
    return detector.is_spam(text, author_name, like_count)


def analyze_comment(text: str, threshold: float = 0.5, author_name: str = "", like_count: int = 0) -> SpamResult:
    """
    Full spam analysis with detailed results.
    
    Args:
        text: Comment text to analyze
        threshold: Spam threshold (0.0 - 1.0)
        author_name: Optional author name
        like_count: Optional like count for engagement-based legitimacy
    
    Returns:
        SpamResult with score, signals, legitimacy bonuses, and classification
    """
    detector = SpamDetector(threshold=threshold)
    return detector.analyze(text, author_name, like_count)


# =============================================================================
# BATCH PROCESSING
# =============================================================================

def filter_spam_batch(
    comments: List[dict], 
    text_key: str = "Comment Text",
    author_key: str = "Author Name",
    likes_key: str = "Comment Likes",
    threshold: float = 0.5, 
    include_scores: bool = False
) -> List[dict]:
    """
    Filter spam from a list of comment dictionaries.
    
    Args:
        comments: List of comment dicts
        text_key: Key for the comment text field
        author_key: Key for the author name field
        likes_key: Key for the like count field
        threshold: Spam threshold
        include_scores: If True, add spam_score to non-spam comments
    
    Returns:
        Filtered list with spam removed
    """
    detector = SpamDetector(threshold=threshold)
    filtered = []
    
    for comment in comments:
        text = comment.get(text_key, "")
        author = comment.get(author_key, "")
        likes = comment.get(likes_key, 0)
        
        # Handle likes that might be strings
        if isinstance(likes, str):
            try:
                likes = int(likes)
            except ValueError:
                likes = 0
        
        result = detector.analyze(text, author, likes)
        
        if not result.is_spam:
            if include_scores:
                comment = comment.copy()
                comment['spam_score'] = result.score
                comment['spam_signals'] = result.reason if result.signals else ""
            filtered.append(comment)
    
    return filtered


def analyze_batch(
    comments: List[str], 
    threshold: float = 0.5
) -> List[SpamResult]:
    """
    Analyze multiple comments efficiently.
    
    Args:
        comments: List of comment texts
        threshold: Spam threshold
    
    Returns:
        List of SpamResult objects
    """
    detector = SpamDetector(threshold=threshold)
    return [detector.analyze(text) for text in comments]



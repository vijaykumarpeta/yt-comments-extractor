# Release Notes

## Version 2.1.0 (May 2026)

**Smarter spam detection, UI refinements, and comprehensive code quality improvements.**

This release strengthens the spam filter with three new detection layers — duplicate campaign detection, signal combination boosts, and structural analysis — while polishing the UI with brand identity and clearer labeling. Under the hood, 23 code quality issues have been fixed and a full test suite has been added.

---

### ✨ New Features

#### Spam Campaign Detection
Detects duplicate and near-duplicate comment clusters that indicate coordinated spam campaigns:
- **Exact duplicate grouping**: Identical comments (after normalization) are grouped in O(n) time
- **Near-duplicate matching**: Comments with 85%+ similarity are clustered using sequence matching
- Clusters of 3+ comments are automatically flagged as campaign spam
- Integrated into batch processing — enabled by default, configurable via `detect_campaigns` parameter
- Case-insensitive and punctuation-normalized for robust matching

#### Signal Combination Boosts
Certain signal pairs are far more diagnostic together than individually. Eight high-confidence combinations now receive score boosts:

| Signal Pair | Boost |
|-------------|-------|
| Crypto + Contact Solicitation | +0.15 |
| Crypto + Platform Redirect | +0.15 |
| Financial Scam + Contact Solicitation | +0.15 |
| Financial Scam + Platform Redirect | +0.15 |
| Impersonation + Platform Redirect | +0.15 |
| Channel Promotion + Shortened URL | +0.12 |
| Self-Promotion + Shortened URL | +0.12 |
| Crypto + Financial Scam | +0.10 |

The highest matching boost is applied (not cumulative), preventing runaway scores.

#### Structural / Character Density Analysis
Three new amplifier signals detect spam-associated text patterns:
- **Spam emoji clusters**: Flags comments with 3+ spam-associated emoji (💰🚀🔥💎📈 etc.) at 8%+ density
- **Excessive caps ratio**: Flags 70%+ uppercase text, but only when other spam signals are present
- **Repetitive punctuation**: Detects "!!!" and "???" patterns as amplifiers

These are **amplifiers only** — they never trigger spam classification on their own, so enthusiastic genuine comments (ALL CAPS excitement, emoji reactions) are not affected.

---

### 🎨 UI Changes

- **Header redesign**: "by Creator Intelligence" brand attribution below the title, with updated tagline
- **Filter Words label**: Changed to "Only fetch comments with these words" for clarity
- **Fetch Comments button**: Text color changed to black for better contrast on accent background

---

### 🔧 Code Quality Improvements

23 issues identified and fixed across all severity levels:

**Critical:**
- Fixed race condition in `_on_closing` — background thread is now joined before window destruction
- Fixed `FetchState.cancel_event` type annotation (`Optional[threading.Event]`)
- Cancellation event now passed through to `fetch_comments()` pagination loop

**High:**
- Thread-safe singleton for default spam detector (double-checked locking)
- String-matching error handling replaced with typed exception catches
- Export methods now snapshot data under lock to prevent concurrent modification
- Removed dead `raise` after `_handle_http_error` in extractor
- Settings file path now resolves relative to app directory (not CWD)

**Medium:**
- Leetspeak normalization rewritten per-word — only normalizes chars embedded between alpha chars (prevents "$5000" → "ssooo")
- Deobfuscation refined: only strips dots/underscores/backticks (preserves apostrophes/hyphens), raised threshold to 50% ratio
- Pre-compiled words filter pattern for batch performance
- Removed unused `ExtractionResult` dataclass
- Removed no-op legacy sort migration
- Fixed window height default to use constant
- Moved `SpamFilterStrength` import to top of spam_filter.py

**Low:**
- Added `MaxCommentsValidator` and `WordsFilterValidator` to core package exports
- Simplified scroll guard to direct method reference
- `save_to_csv` and `save_to_excel` now return `List[str]` of files written
- Fixed `_get_date_range` return type to `Tuple` (capital T)
- Removed redundant string comparisons in `_sort_comments`
- `to_dict` now preserves `None` values for settings round-trip

---

### 🧪 Test Suite

Added comprehensive test coverage (138 tests):

| Module | Tests | Coverage |
|--------|-------|----------|
| Spam Filter | 83 | Normalization, homoglyphs, all 15 spam categories, legitimacy signals, thresholds, custom patterns, batch processing, signal combos, structural analysis, campaign detection |
| Validators | 55 | URL validation (all formats), date ranges, API keys, min likes, max comments, words filter with pre-compilation |

---

### 📊 Technical Statistics

| Metric | v2.0.0 | v2.1.0 |
|--------|--------|--------|
| Spam Detection Categories | 13 | 15 |
| Pre-compiled Regex Patterns | 25+ | 27+ |
| Signal Combination Rules | — | 8 |
| Test Cases | — | 138 |
| Files Changed | — | 9 |
| Lines Added | — | 430+ |

---

### 📝 Full Changelog

**Added:**
- Spam campaign detection (duplicate/near-duplicate clustering)
- Signal combination boosts for 8 high-confidence signal pairs
- Structural spam analysis (emoji density, caps ratio, repetitive punctuation)
- `STRUCTURAL_SPAM` and `SPAM_CAMPAIGN` spam categories
- `detect_spam_campaigns()` function for batch-level campaign detection
- `detect_campaigns` and `campaign_min_cluster` parameters to `filter_spam_batch()`
- `SPAM_EMOJI` constant set for spam-associated emoji
- Brand attribution ("by Creator Intelligence") in header
- 138 tests across spam filter and validators
- `tests/` directory with `test_spam_filter.py` and `test_validators.py`

**Changed:**
- Version bumped to 2.1.0
- App tagline updated to "Extract and filter YouTube comments into a clean, research-ready dataset."
- "Filter Words" label changed to "Only fetch comments with these words"
- Fetch Comments button text color changed to black
- Header height increased to accommodate brand line
- README updated with new spam detection features, fixed sensitivity threshold table, added tests to project structure

**Fixed:**
- Race condition in window close with active fetch thread
- Leetspeak normalization false positives on standalone numbers and symbols
- Settings file path resolution when run from different working directory
- Thread safety for default spam detector singleton
- 23 code quality issues across all modules (see Code Quality Improvements above)

---

## Version 2.0.0 (December 2025)

**A complete rewrite with modular architecture, advanced spam detection, and powerful filtering capabilities.**

This release represents a major evolution of the YouTube Comment Extractor. The codebase has been restructured for maintainability, the spam detection system has been completely reimagined, and new filtering features make it easier than ever to extract exactly the comments you need.

---

### ✨ New Features

#### Filter Words (Keyword Search)
Extract only comments containing specific keywords — perfect for topic-focused research:
- Enter comma-separated words: `python, tutorial, beginner`
- **Whole-word matching**: Searching for "python" won't match "pythonic"
- **Case-insensitive**: "Python" matches "python"
- **OR logic**: Comment is included if it contains ANY of the specified words

Use cases:
- Topic research: Find comments about "pricing", "tutorial", "beginner"
- Feedback analysis: Extract comments mentioning "bug", "feature", "suggestion"
- Sentiment tracking: Search for "love", "hate", "amazing", "terrible"

#### Max Comments Limit
Control exactly how many comments to extract per video:
- Set a specific limit (e.g., 500 comments per video)
- Leave empty for unlimited extraction
- Great for quick sampling or managing API quota

#### Custom Blacklist/Whitelist Patterns
Define your own spam filtering rules:
- **Blacklist**: Patterns that always flag comments as spam
- **Whitelist**: Patterns that always allow comments through (bypass spam detection)
- Patterns are matched case-insensitively
- Accessible via dedicated dialog buttons in the sidebar

#### Secure API Key Storage
Your API key is now stored securely using your operating system's credential manager:
- **Windows**: Credential Manager
- **macOS**: Keychain
- **Linux**: Secret Service (GNOME Keyring, KWallet, etc.)
- Falls back to file storage if keyring is unavailable
- Visual "🔒 Secure" indicator when keyring is active

#### Enhanced Spam Detection
The spam filter has been completely rewritten with a multi-signal scoring architecture:

| Category | Description |
|----------|-------------|
| Crypto/Financial Scams | Bitcoin, forex, seed phrase scams, fake giveaways |
| Contact Solicitation | WhatsApp, Telegram, phone numbers, email harvesting |
| Self-Promotion | Aggressive channel plugs, "check my video" spam |
| Impersonation | Fake verification badges, creator impersonation |
| Platform Redirect | t.me links, wa.me links, Discord invites |
| Book/Product Promotion | Amazon links, "buy my course" spam |
| Bot Patterns | Repetitive templates, generic praise + promo |
| Obfuscation | Cyrillic homoglyphs, leetspeak, zero-width characters |

**Legitimacy Signals** — Comments showing genuine engagement receive score reductions:
- Timestamp references (e.g., "at 5:32")
- Questions and discussion
- High engagement (many likes)
- Long, thoughtful content
- Educational context

#### Adjustable Spam Sensitivity
Slider control to adjust filter aggressiveness:
- **Light** (0.65): Only obvious spam, minimal false positives
- **Moderate** (0.50): Balanced filtering (default)
- **Aggressive** (0.35): Stricter filtering, catches more spam

#### Thread-Safe Cancellation
- Cancel button appears during fetch operations
- Uses `threading.Event()` for clean cancellation
- No more frozen UI or orphaned threads

#### Extended URL Format Support
Now supports all YouTube URL formats:
- `youtube.com/watch?v=VIDEO_ID`
- `youtube.com/v/VIDEO_ID`
- `youtube.com/embed/VIDEO_ID`
- `youtube.com/shorts/VIDEO_ID`
- `youtu.be/VIDEO_ID`

#### Type Hints Throughout
The entire codebase now includes type hints for better IDE support and maintainability.

---

### 🔧 Improvements

#### Refactored Architecture
The codebase has been reorganized into a modular structure:

```
yt-comments-extractor/
├── main.py              # GUI application
├── extractor.py         # YouTube API wrapper
├── spam_filter.py       # Spam detection engine
└── core/
    ├── __init__.py      # Package exports
    ├── constants.py     # Centralized configuration
    ├── settings.py      # Settings with keyring support
    └── validators.py    # Input validation utilities
```

#### Enhanced Input Validation
- Real-time URL validation with visual feedback
- Date range validation (prevents "from" after "to")
- Min likes validation with helpful warnings
- API key format checking

#### Improved Error Handling
- Specific error messages for API quota exceeded
- Clear handling of disabled comments
- Better error propagation throughout the codebase
- No more silent failures

#### Suppressed API Warnings
- Google API client discovery cache warnings are now silenced
- Cleaner console output

#### Optimized UI Layout
- Two-panel layout with settings sidebar
- Better spacing and alignment
- Cleaner filter section organization
- Improved activity log with auto-scroll
- Footer shows keyboard shortcuts and version

#### Unicode Normalization
The spam filter applies comprehensive text normalization before detection:
1. Removes zero-width characters (used to break up keywords)
2. Converts Cyrillic/Greek homoglyphs to Latin equivalents
3. Applies NFKD Unicode normalization (handles ligatures, accents)
4. Selectively normalizes leetspeak patterns
5. Removes obfuscation punctuation (t.e.l.e.g.r.a.m → telegram)


### 📊 Technical Statistics

| Metric | Value |
|--------|-------|
| Total Lines of Code | ~3,500 |
| Main Application | 1,513 lines |
| Spam Filter Engine | 1,257 lines |
| YouTube API Wrapper | 618 lines |
| Core Utilities | ~350 lines |
| Pre-compiled Regex Patterns | 25+ |
| Spam Detection Categories | 13 |
| Input Validators | 6 |

---

### ⬆️ Upgrade Guide

#### From v1.x

1. **Backup your `settings.json`** (if you have one)
2. Clone or download v2.0.0
3. Install updated dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Your API key will be migrated automatically on first run
5. Consider installing keyring for secure storage:
   ```bash
   pip install keyring
   ```

#### Configuration Changes

**New settings stored:**
- `max_comments`: Maximum comments per video (null = unlimited)
- `filter_words`: Comma-separated filter words
- `blacklist_patterns`: Custom blacklist (string, newline-separated)
- `whitelist_patterns`: Custom whitelist (string, newline-separated)
- `spam_threshold`: Detection sensitivity (float, 0.0-1.0)

**Removed settings:**
- Legacy spam filter strength enum (replaced with threshold)

---

### 🔮 Roadmap

Features under consideration for future releases:
- Reply extraction (nested comment threads)
- Transcript extraction from videos
- API rate limit monitoring

---

### 📝 Full Changelog

**Added:**
- Filter Words feature for keyword-based comment extraction
- Max Comments limit per video
- Custom blacklist/whitelist pattern support
- Secure keyring storage for API keys
- Multi-signal spam detection with 13 categories
- Legitimacy signals for genuine comment protection
- Unicode normalization (Cyrillic homoglyphs, NFKD, leetspeak)
- Thread-safe cancellation with `threading.Event()`
- Adjustable spam sensitivity slider (Light/Moderate/Aggressive)
- Two-panel UI layout with settings sidebar
- Secure storage indicator in UI
- Type hints throughout codebase
- Comprehensive input validation
- Modular architecture with `core/` package
- Extended YouTube URL format support
- Real-time URL validation in UI
- Auto-scrolling activity log
- Suppressed Google API cache warnings

**Changed:**
- Complete rewrite of spam detection engine
- Refactored settings management
- Improved error handling and propagation
- Enhanced UI layout and spacing
- Better API error messages
- Optimized regex pattern compilation
- Window default height adjusted for better fit

**Removed:**
- Legacy spam filter strength enum
- Print statements replaced with proper logging

---

### 📄 License

MIT License — see [LICENSE](LICENSE) file for details.

---

**Thank you for using YouTube Comment Extractor!**

Report issues: [GitHub Issues](https://github.com/vijaykumarpeta/yt-comments-extractor/issues)

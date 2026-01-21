"""
Pattern detection for extracting transmittal metadata from emails.
Analyzes subject lines, body content, and attachment names.
"""

from typing import Dict, List, Optional
import re
import datetime

from src.modules.drawing_coordinator.config import MIN_ATTACHMENT_SIZE, MAX_ATTACHMENT_SIZE


class EmailPatternDetector:
    """
    Detects and extracts transmittal metadata from email content.

    Reuses TypeDetector patterns but adapted for:
    - Email subject lines
    - Email body text
    - Attachment filenames
    """

    IFA_PATTERNS = [
        "ifa",
        "for_approval",
        "in_for_approval",
        "approval_dwg",
        "review_set",
    ]

    IFA_REGEX = [re.compile(r"\brev[\s_\-]*[A-Z]{1,2}\b", re.IGNORECASE)]

    IFF_PATTERNS = [
        "iff",
        "for_fabrication",
        "fabrication",
        "for_construction",
        "in_for_fabrication",
        "construction_set",
        "fabrication_set",
    ]

    IFF_REGEX = [re.compile(r"rev[\s_\-]*\d+", re.IGNORECASE)]

    EXCLUSION_PATTERNS = [
        # Production Notes
        r"\bproduction\s+note",
        r"\bprod\s+note",
        r"\bp\.n\."

        # Cutlists / Material Lists / Packages
        r"\bcutlist",
        r"\bcut\s+list",
        r"\bcut\s+list\s+request",
        r"\bmaterial\s+list",
        r"\bplease\s+issue\s+a\s+cut",
        r"\bissue\s+cut\s+list",
        r"\bpkg\s*#\s*\d+",  # Package references like "PKG#032"
        r"\bpackage\s*#\s*\d+",

        # Sub-fabricator coordination
        r"\bsub-fabricator",
        r"\bsub\s+fabricator",
        r"\bsub#",

        # RFI / Shop Questions (not transmittals)
        r"\brfi\s*#?\s*\d+",
        r"\brequest\s+for\s+information",

        # Change Orders / Addendums (not initial transmittals)
        r"\bchange\s+order",
        r"\bco\s*#?\s*\d+",
        r"\baddendum",

        # Shop coordination emails
        r"\braw\s+material",
        r"\bpick\s+up\s+from\s+sub",
        r"\bship\s+to\s+sub",
        r"\bbay\s+\d+\s+parts",

        # Bid-related emails (not transmittals)
        r"\bdrawings\s+posted",
        r"\bdd\s+budget",
        r"\bdesign\s+development\s+budget",
        r"\bbid\s+invitation",
        r"\bbe?\s*on\s+the\s+bid",
    ]

    EXCLUSION_REGEX = [re.compile(pattern, re.IGNORECASE) for pattern in EXCLUSION_PATTERNS]

    JOB_NUM_REGEX = re.compile(r"(?<!\d)\d{4}(?!\d)")
    TRANS_REGEX = re.compile(r"(?:\btransmittal|\btr|\bt)[\s#]*0*(\d{1,3})(?=\b|[^0-9])", re.IGNORECASE)

    ZIP_CONTENT_TYPES = [
        "application/zip",
        "application/x-zip-compressed",
        "application/x-zip",
        "application/octet-stream",
    ]

    # Cloud storage link patterns with provider names
    # Format: (provider_name, regex_pattern)
    CLOUD_PROVIDERS = [
        # SharePoint / OneDrive
        ("sharepoint", r"(?:https?://)?[\w.-]*sharepoint\.com/[:\w/_?=&%-]+"),
        ("onedrive", r"(?:https?://)?1drv\.ms/[\w/_?=&%-]+"),
        ("onedrive", r"(?:https?://)?onedrive\.live\.com/[\w/_?=&%-]+"),
        # WeTransfer
        ("wetransfer", r"(?:https?://)?(?:www\.)?wetransfer\.com/downloads/[\w/_?=&%-]+"),
        ("wetransfer", r"(?:https?://)?we\.tl/[\w-]+"),
        # Dropbox
        ("dropbox", r"(?:https?://)?(?:www\.)?dropbox\.com/[\w/_?=&%-]+"),
        ("dropbox", r"(?:https?://)?db\.tt/[\w-]+"),
        # Google Drive
        ("google_drive", r"(?:https?://)?drive\.google\.com/[\w/_?=&%-]+"),
        ("google_drive", r"(?:https?://)?docs\.google\.com/[\w/_?=&%-]+"),
        # Box
        ("box", r"(?:https?://)?(?:www\.)?box\.com/[\w/_?=&%-]+"),
        ("box", r"(?:https?://)?app\.box\.com/[\w/_?=&%-]+"),
        # Hightail (formerly YouSendIt)
        ("hightail", r"(?:https?://)?(?:www\.)?hightail\.com/[\w/_?=&%-]+"),
        ("hightail", r"(?:https?://)?(?:www\.)?yousendit\.com/[\w/_?=&%-]+"),
        # Egnyte
        ("egnyte", r"(?:https?://)?[\w.-]*egnyte\.com/[\w/_?=&%-]+"),
        # Citrix ShareFile
        ("sharefile", r"(?:https?://)?[\w.-]*sharefile\.com/[\w/_?=&%-]+"),
    ]

    CLOUD_LINK_REGEX = [(provider, re.compile(pattern, re.IGNORECASE)) for provider, pattern in CLOUD_PROVIDERS]

    def __init__(self):
        """Initialize pattern detector with regex patterns."""
        self._current_year = str(datetime.datetime.now().year)

    def _normalize_text(self, text: str) -> str:
        """Normalize text for pattern matching."""
        if not text:
            return ""
        return text.lower().replace("-", " ").replace("_", " ")

    def _is_excluded(self, text: str) -> bool:
        """
        Check if text matches exclusion patterns (NOT a transmittal).

        Args:
            text: Text to check (subject, body, etc.)
        Returns:
            True if text matches exclusion pattern, False otherwise
        """
        if not text:
            return False

        normalized = self._normalize_text(text)

        # Check all exclusion patterns
        for pattern in self.EXCLUSION_REGEX:
            if pattern.search(normalized):
                return True

        return False

    def _normalize_cloud_link(self, link: str) -> str:
        """
        Normalize a cloud link that may have been mangled by email security software.
        Ensures link has https:// prefix.
        """
        if not link:
            return link

        # Already has protocol
        if link.startswith("https://") or link.startswith("http://"):
            return link

        # Missing protocol - add https://
        return f"https://{link}"

    def _extract_cloud_links(self, text: str) -> List[Dict]:
        """
        Extract cloud storage links (SharePoint, OneDrive, Dropbox, WeTransfer, etc.) from text.
        Also detects email security scanner links (Trustifi, Cisco, etc.) that wrap download URLs.

        Args:
            text: Text to search (usually email body HTML)
        Returns:
            List of detected cloud storage links with metadata:
            [
                {
                    "link": "https://sharepoint.com/...",
                    "provider": "sharepoint",
                    "raw_match": "sharepoint.com/...",
                    "anchor_text": "filename.zip"  # if detected from anchor
                }
            ]
        """
        if not text:
            return []

        found_links = []
        seen_links = set()

        for provider, pattern in self.CLOUD_LINK_REGEX:
            matches = pattern.findall(text)
            for match in matches:
                normalized = self._normalize_cloud_link(match)
                if normalized not in seen_links:
                    seen_links.add(normalized)
                    found_links.append({
                        "link": normalized,
                        "provider": provider,
                        "raw_match": match
                    })

        anchor_pattern = re.compile(
            r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]*)</a>',
            re.IGNORECASE | re.DOTALL
        )
        anchor_matches = anchor_pattern.findall(text)

        for url, anchor_text in anchor_matches:
            anchor_text = anchor_text.strip()

            matched_provider = None
            for provider, pattern in self.CLOUD_LINK_REGEX:
                if pattern.search(url):
                    matched_provider = provider
                    break

            if matched_provider:
                normalized = self._normalize_cloud_link(url)
                if normalized not in seen_links:
                    seen_links.add(normalized)
                    link_entry = {
                        "link": normalized,
                        "provider": matched_provider,
                        "raw_match": url
                    }
                    if anchor_text:
                        link_entry["anchor_text"] = anchor_text
                    found_links.append(link_entry)

            # These wrap the actual download link but clicking them redirects properly
            elif self._is_security_scanner_link(url):
                if anchor_text and self._is_download_anchor(anchor_text):
                    normalized = self._normalize_cloud_link(url)
                    if normalized not in seen_links:
                        seen_links.add(normalized)
                        found_links.append({
                            "link": normalized,
                            "provider": "security_scanner",
                            "raw_match": url,
                            "anchor_text": anchor_text,
                            "note": "Link wrapped by email security scanner - opens in browser"
                        })

        return found_links

    def _is_security_scanner_link(self, url: str) -> bool:
        """
        Check if URL is from an email security scanning service.
        These services wrap links for security scanning but redirect to the original.
        """
        security_scanners = [
            "trustifi.com",
            "onclickscan.trustifi.com",
            "secure-web.cisco.com",
            "urldefense.proofpoint.com",
            "safelinks.protection.outlook.com",
            "clicktime.symantec.com",
            "urlscan.io",
        ]
        url_lower = url.lower()
        return any(scanner in url_lower for scanner in security_scanners)

    def _is_download_anchor(self, anchor_text: str) -> bool:
        """
        Check if anchor text suggests a downloadable file.
        """
        if not anchor_text:
            return False

        anchor_lower = anchor_text.lower()

        # Check for file extensions
        download_extensions = ['.zip', '.rar', '.7z', '.pdf', '.dwg', '.dxf']
        if any(ext in anchor_lower for ext in download_extensions):
            return True

        # Check for transmittal keywords
        transmittal_keywords = ['transmittal', 'tr#', 't#', 'download', 'click here to download']
        if any(kw in anchor_lower for kw in transmittal_keywords):
            return True

        return False

    def _extract_job_number(self, text: str) -> Optional[str]:
        """Extract 4-digit job number from text, excluding current year."""
        normalized = self._normalize_text(text)
        matches = self.JOB_NUM_REGEX.findall(normalized)

        for match in matches:
            if match != self._current_year:
                return match
        return None

    def _extract_transmittal_number(self, text: str) -> Optional[str]:
        """Extract transmittal number and format as T###."""
        normalized = self._normalize_text(text)
        match = self.TRANS_REGEX.search(normalized)

        if match:
            return f"T{int(match.group(1)):03d}"
        return None

    def _detect_type(self, text: str) -> Optional[str]:
        """Detect IFA or IFF from text."""
        normalized = self._normalize_text(text)

        ifa_score = 0
        iff_score = 0

        # Check keyword patterns
        if any(term in normalized for term in self.IFA_PATTERNS):
            ifa_score += 2
        if any(rgx.search(normalized) for rgx in self.IFA_REGEX):
            ifa_score += 1

        if any(term in normalized for term in self.IFF_PATTERNS):
            iff_score += 2
        if any(rgx.search(normalized) for rgx in self.IFF_REGEX):
            iff_score += 1

        if ifa_score > iff_score and ifa_score > 0:
            return "IFA"
        elif iff_score > ifa_score and iff_score > 0:
            return "IFF"
        return None

    def _create_detection_result(
            self,
            job_number: Optional[str] = None,
            transmittal_number: Optional[str] = None,
            transmittal_type: Optional[str] = None
    ) -> Dict:
        """Create a standardized detection result dictionary."""
        # Calculate confidence based on how many fields were detected
        detected_count = sum(1 for x in [job_number, transmittal_number, transmittal_type] if x)

        if detected_count >= 2:
            confidence = "high"
        elif detected_count == 1:
            confidence = "medium"
        else:
            confidence = "low"

        return {
            "job_number": job_number,
            "transmittal_number": transmittal_number,
            "transmittal_type": transmittal_type,
            "confidence": confidence
        }

    def detect_from_subject(self, subject: str) -> Dict:
        """
        Extract transmittal metadata from email subject line.

        Args:
            subject: Email subject line

        Returns:
            {
                "job_number": "6509" or None,
                "transmittal_number": "T022" or None,
                "transmittal_type": "IFF" or "IFA" or None,
                "confidence": "high" or "medium" or "low",
                "excluded": False or True
            }
        """
        if not subject:
            return self._create_detection_result()

        # Quick exclusion check
        if self._is_excluded(subject):
            result = self._create_detection_result()
            result["excluded"] = True
            result["confidence"] = "low"
            return result

        job_number = self._extract_job_number(subject)
        transmittal_number = self._extract_transmittal_number(subject)
        transmittal_type = self._detect_type(subject)

        result = self._create_detection_result(job_number, transmittal_number, transmittal_type)
        result["excluded"] = False
        return result

    def detect_from_body(self, body: str) -> Dict:
        """
        Extract transmittal metadata from email body content.

        Args:
            body: Email body text (plain text or HTML)

        Returns:
            Same structure as detect_from_subject
        """
        if not body:
            return self._create_detection_result()

        # Strip common HTML tags for cleaner text analysis
        clean_body = re.sub(r'<[^>]+>', ' ', body)

        job_number = self._extract_job_number(clean_body)
        transmittal_number = self._extract_transmittal_number(clean_body)
        transmittal_type = self._detect_type(clean_body)

        return self._create_detection_result(job_number, transmittal_number, transmittal_type)

    def detect_from_attachment_names(self, attachments: List[Dict]) -> Dict:
        """
        Analyze attachment filenames for transmittal metadata.

        Args:
            attachments: List of attachment objects with 'name' field

        Returns:
            Same structure as detect_from_subject
        """
        if not attachments:
            return self._create_detection_result()

        # Combine all attachment names for analysis
        all_names = " ".join(att.get("name", "") for att in attachments)

        job_number = self._extract_job_number(all_names)
        transmittal_number = self._extract_transmittal_number(all_names)
        transmittal_type = self._detect_type(all_names)

        return self._create_detection_result(job_number, transmittal_number, transmittal_type)

    def analyze_email(self, subject: str, body: str, attachments: List[Dict]) -> Dict:
        """
        Comprehensive analysis combining all detection methods.

        Args:
            subject: Email subject line
            body: Email body text
            attachments: List of attachment objects

        Returns:
            {
                "job_number": "6509",
                "transmittal_number": "T022",
                "transmittal_type": "IFF",
                "confidence": "high",
                "detected_from": ["subject", "attachments"],
                "is_transmittal": true,
                "excluded": false,
                "exclusion_reason": None,
                "cloud_links": ["https://sharepoint.com/..."]
            }
        """

        combined_text = f"{subject} {body}"
        if self._is_excluded(combined_text):
            return {
                "job_number": None,
                "transmittal_number": None,
                "transmittal_type": None,
                "confidence": "low",
                "detected_from": [],
                "is_transmittal": False,
                "excluded": True,
                "exclusion_reason": "Matched exclusion pattern (cutlist, production note, RFI, etc.)",
                "cloud_links": []
            }

        cloud_links = self._extract_cloud_links(body)

        # Extract just the link URLs for backward compatibility checks
        cloud_link_urls = [cl["link"] for cl in cloud_links]

        subject_result = self.detect_from_subject(subject)
        body_result = self.detect_from_body(body)
        attachment_result = self.detect_from_attachment_names(attachments)

        detections = [
            ("subject", subject_result),
            ("body", body_result),
            ("attachments", attachment_result)
        ]

        final_job = None
        final_trans = None
        final_type = None
        detected_from = []

        for source_name, result in detections:
            if result["job_number"] and not final_job:
                final_job = result["job_number"]
                detected_from.append(source_name)

            if result["transmittal_number"] and not final_trans:
                final_trans = result["transmittal_number"]
                if source_name not in detected_from:
                    detected_from.append(source_name)

            if result["transmittal_type"] and not final_type:
                final_type = result["transmittal_type"]
                if source_name not in detected_from:
                    detected_from.append(source_name)

        confidence = self.calculate_confidence([subject_result, body_result, attachment_result])

        has_transmittal_attachment = any(
            self.is_likely_transmittal_attachment(att) for att in (attachments or [])
        )

        has_cloud_link = len(cloud_links) > 0

        if has_cloud_link and (final_job or final_trans or final_type):
            if "cloud_links" not in detected_from:
                detected_from.append("cloud_links")
            confidence = "high"

        is_transmittal = (
                (has_transmittal_attachment or has_cloud_link) and
                (final_job is not None or final_trans is not None or final_type is not None)
        )

        return {
            "job_number": final_job,
            "transmittal_number": final_trans,
            "transmittal_type": final_type,
            "confidence": confidence,
            "detected_from": detected_from,
            "is_transmittal": is_transmittal,
            "excluded": False,
            "exclusion_reason": None,
            "cloud_links": cloud_links  # Now returns structured list with provider info
        }

    def calculate_confidence(self, detections: List[Dict]) -> str:
        """
        Calculate overall confidence based on multiple detection sources.

        Args:
            detections: List of detection results from different sources

        Returns:
            "high" if multiple sources agree
            "medium" if single source
            "low" if uncertain or conflicting
        """
        # Count sources that found each field
        job_sources = sum(1 for d in detections if d.get("job_number"))
        trans_sources = sum(1 for d in detections if d.get("transmittal_number"))
        type_sources = sum(1 for d in detections if d.get("transmittal_type"))

        # Check conflicts
        job_values = set(d.get("job_number") for d in detections if d.get("job_number"))
        trans_values = set(d.get("transmittal_number") for d in detections if d.get("transmittal_number"))
        type_values = set(d.get("transmittal_type") for d in detections if d.get("transmittal_type"))

        has_conflicts = len(job_values) > 1 or len(trans_values) > 1 or len(type_values) > 1

        if has_conflicts:
            return "low"

        # High confidence: multiple sources agree on at least 2 fields
        agreeing_fields = sum(1 for count in [job_sources, trans_sources, type_sources] if count >= 2)
        if agreeing_fields >= 2:
            return "high"

        # Medium confidence: at least one field detected
        total_detected = job_sources + trans_sources + type_sources
        if total_detected >= 1:
            return "medium"

        return "low"

    def is_likely_transmittal_attachment(self, attachment: Dict) -> bool:
        """
        Determine if an attachment is likely a transmittal ZIP.

        Args:
            attachment: Attachment object with name, size, contentType
        Returns:
            True if likely a transmittal, False otherwise
        """
        if not attachment:
            return False

        name = attachment.get("name", "").lower()
        size = attachment.get("size", 0)
        content_type = attachment.get("contentType", "").lower()
        is_inline = attachment.get("isInline", False)

        if is_inline:
            return False

        # Must be a ZIP file
        is_zip = name.endswith(".zip") or content_type in self.ZIP_CONTENT_TYPES
        if not is_zip:
            return False

        # Check size limits for email attachments
        if size < MIN_ATTACHMENT_SIZE or size > MAX_ATTACHMENT_SIZE:
            return False

        # check if filename contains transmittal indicators
        normalized_name = self._normalize_text(name)
        has_job = self._extract_job_number(name) is not None
        has_trans = self._extract_transmittal_number(name) is not None
        has_type = self._detect_type(name) is not None

        if has_job or has_trans or has_type:
            return True

        return True

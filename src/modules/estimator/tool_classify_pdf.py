"""
Classify PDF — Wraps the plan_classification engine for agent execution

Full pipeline:
  Phase 1: Auto-detect title block region
  Phase 2: Classify every page by construction discipline
  Phase 3: AI directory naming from PDF filename
  Phase 4: Date extraction (text → OCR → vision)
  Phase 5: Breakout into per-discipline PDFs with date-prefixed filenames
"""
import os
from typing import Any

from anthropic import Anthropic

from plan_classification import (
    ClassificationEngine,
    PipelineConfig,
    BreakoutHandler,
    AISummaryService,
    DateExtractor,
    get_pdf_page_count,
)

from src.modules.estimator.config import (
    DEFAULT_OUTPUT_PATH,
    DEFAULT_MAX_WORKERS,
    DEFAULT_MAX_IMAGE_DIM,
    DEFAULT_OCR_ZOOM,
)


# Disciplines included in "standard" breakout mode
# Civil sub-disciplines (CG, CS, CU, etc.) are intentionally excluded
STANDARD_DISCIPLINES = {
    'Architectural', 'Architectural - Interiors', 'Architectural - Finishes',
    'Structural',
    'Landscape',
    'Civil',
    'Unknown',
}


def classify_and_breakout(
        pdf_path: str,
        anthropic_api_key: str,
        output_path: str | None = None,
        breakout_filter: str = 'all' ) -> dict[str, Any]:
    """Classify a PDF then split it into per-discipline files"""

    if not os.path.exists(pdf_path):
        return {"success": False, "error": f"PDF not found: {pdf_path}"}

    page_count = get_pdf_page_count(pdf_path)
    if page_count == 0:
        return {"success": False, "error": "PDF has no pages"}

    # ── Phase 1+2: Region detection + Classification ──────────────
    config = PipelineConfig(
        anthropic_api_key   = anthropic_api_key,
        max_workers         = DEFAULT_MAX_WORKERS,
        max_image_dimension = DEFAULT_MAX_IMAGE_DIM,
        ocr_zoom            = DEFAULT_OCR_ZOOM,
    )

    engine  = ClassificationEngine(config)
    results = engine.classify(pdf_path)

    serialized = [_serialize_result(r) for r in results]

    # ── Shared AI client ──────────────────────────────────────────
    ai_client = Anthropic(api_key=anthropic_api_key)

    # ── Phase 3: AI Directory Naming ──────────────────────────────
    out_dir    = output_path or str(DEFAULT_OUTPUT_PATH)
    ai_dirname = _generate_dirname(ai_client, pdf_path)

    if ai_dirname:
        out_dir = os.path.join(out_dir, ai_dirname)

    os.makedirs(out_dir, exist_ok=True)

    # ── Phase 4: Date Extraction ──────────────────────────────────
    date_map = _extract_dates(ai_client, pdf_path, results)

    # ── Phase 5: Breakout ─────────────────────────────────────────
    breakout_results = _merge_general_to_arch(serialized)

    if breakout_filter == 'standard':
        breakout_results = [
            r for r in breakout_results
            if (r.get('discipline') or r.get('category', 'Unknown')) in STANDARD_DISCIPLINES
        ]

    handler = BreakoutHandler(
        classification_results=breakout_results,
        pdf_path=pdf_path,
        output_dir=out_dir,
    )

    breakout_result = handler.breakout(date_map=date_map)

    # Split merged Architectural back for display
    if breakout_result.get('created_files'):
        breakout_result['created_files'] = _split_general_display(
            breakout_result['created_files'],
            serialized,
        )

    # ── Summary ───────────────────────────────────────────────────
    summary = _build_summary(results, engine, breakout_result)

    return {
        "success":        True,
        "pdf_path":       pdf_path,
        "page_count":     page_count,
        "results":        serialized,
        "breakout":       breakout_result,
        "output_path":    out_dir,
        "ai_dirname":     ai_dirname,
        "summary":        summary,
        "timings":        engine.timings,
    }


# =============================================================================
# Phase 3: AI Directory Naming
# =============================================================================

def _generate_dirname(client: Anthropic, pdf_path: str) -> str | None:
    """Use AI to generate a clean project directory name from the PDF filename"""

    try:
        service    = AISummaryService(client=client)
        filename   = os.path.basename(pdf_path)
        dir_result = service.create_dirname(filename)
        dirname    = dir_result.dir_name.strip()
        dirname    = "".join(c for c in dirname if c not in r'<>:"/\|?*').strip('. ')

        return dirname if dirname else None

    except Exception:
        return None


# =============================================================================
# Phase 4: Date Extraction
# =============================================================================

def _extract_dates(client: Anthropic, pdf_path: str, results: list) -> dict | None:
    """Extract per-discipline dates using tiered approach"""

    try:
        extractor = DateExtractor(anthropic_client=client)
        date_map  = extractor.extract_all(pdf_path, results)

        return date_map

    except Exception:
        return None


# =============================================================================
# Phase 5: Breakout Helpers
# =============================================================================

def _merge_general_to_arch(results: list[dict]) -> list[dict]:
    """Merge General pages into Architectural for breakout"""

    return [
        {**r, 'discipline': 'Architectural'}
        if (r.get('discipline') or r.get('category', 'Unknown')) == 'General'
        else r
        for r in results
    ]


def _split_general_display(
        created_files: list[dict],
        original_results: list[dict] ) -> list[dict]:
    """Split merged Architectural back into separate display rows.

    BreakoutHandler produces one Architectural PDF containing both.
    This restores separate rows so the caller sees Architectural + General
    with individual page counts, both pointing to the same output file.
    """

    if not created_files:
        return created_files

    arch_entry = next((f for f in created_files if f['discipline'] == 'Architectural'), None)
    if not arch_entry:
        return created_files

    general_indices = [
        r.get('page_index', r.get('page_num', 0))
        for r in original_results
        if (r.get('discipline') or r.get('category', 'Unknown')) == 'General'
    ]

    if not general_indices:
        return created_files

    arch_indices = [
        r.get('page_index', r.get('page_num', 0))
        for r in original_results
        if (r.get('discipline') or r.get('category', 'Unknown')) == 'Architectural'
    ]

    output_path = arch_entry['output_path']
    created_files.remove(arch_entry)

    if arch_indices:
        created_files.append({
            'discipline':   'Architectural',
            'page_count':   len(arch_indices),
            'output_path':  output_path,
            'page_numbers': sorted(p + 1 for p in arch_indices),
        })

    created_files.append({
        'discipline':   'General',
        'page_count':   len(general_indices),
        'output_path':  output_path,
        'page_numbers': sorted(p + 1 for p in general_indices),
    })

    return created_files


# =============================================================================
# Summary
# =============================================================================

def _build_summary(results: list, engine, breakout_result: dict | None) -> dict:
    """Build summary statistics from classification results"""

    total_pages = len(results)

    discipline_counts: dict[str, int] = {}
    for r in results:
        disc = getattr(r, 'discipline', None) or 'Unknown'
        discipline_counts[disc] = discipline_counts.get(disc, 0) + 1

    method_counts: dict[str, int] = {}
    for r in results:
        method = getattr(r, 'method', 'unknown')
        method_counts[method] = method_counts.get(method, 0) + 1

    return {
        'total_pages':       total_pages,
        'discipline_counts': discipline_counts,
        'method_counts':     method_counts,
        'timings':           engine.timings,
        'created_files':     breakout_result,
    }


# =============================================================================
# Serialization
# =============================================================================

def _serialize_result(result) -> dict:
    """Convert a PageResult to a plain dict for JSON transport"""

    if isinstance(result, dict):
        return result

    return {
        "page_index":   getattr(result, 'page_index', None),
        "discipline":   getattr(result, 'discipline', None),
        "sheet_number": getattr(result, 'sheet_number', None),
        "confidence":   getattr(result, 'confidence', None),
        "method":       getattr(result, 'method', None),
    }

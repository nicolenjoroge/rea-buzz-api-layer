import logging
import re

from datetime import datetime

log = logging.getLogger("dashboard")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def first_value(item, candidates, default=None):
    """Return first non-empty value from candidates list."""
    for key in candidates:
        if key in item and item[key] not in (None, ""):
            return item[key]
    return default


def parse_number(value, default=0):
    """Parse various number formats (with K, M suffixes, currency, etc.)"""
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        text = (
            text.replace(",", "")
                .replace("KES", "")
                .replace("kes", "")
                .replace(" ", "")
        )
        if text.endswith(("M", "m")):
            return float(text[:-1]) * 1_000_000
        if text.endswith(("K", "k")):
            return float(text[:-1]) * 1_000
        try:
            return float(text)
        except ValueError:
            match = re.search(r"-?\d+(?:\.\d+)?", text)
            return float(match.group(0)) if match else default
    return default


def format_currency(value):
    num = parse_number(value, None)
    if num in (None, 0):
        return ""
    return f"KES {num:,.0f}"


def normalize_date(value):
    """Convert DD-MM-YYYY or DD/MM/YYYY to YYYY-MM-DD for HTML date inputs."""
    if not value:
        return ""

    if isinstance(value, str):
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value.strip(), fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
    return value

def has_value(v):
    """Return True if v is a meaningful, non-zero, non-empty value."""
    if v is None or v == "":
        return False
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, (int, float)):
        return v != 0
    return bool(v)

def pick_quant_benefit(item):
    """
    Return (formatted_text, type_label) for the first available
    quantitative benefit in priority order:
        cost savings → paper savings → man hours → TAT reduction
    """
    cost_value = first_value(
        item, ["cost_savings", "costSavings", "estimated_cost_savings"], None
    )
    if has_value(cost_value):
        return format_currency(cost_value) + " cost savings", "Cost Savings"

    paper_value = first_value(
        item, ["paper_savings", "paper_and_printing_savings"], None
    )
    if has_value(paper_value):
        return format_currency(paper_value) + " paper cost savings", "Paper Savings"

    man_hours_value = first_value(
        item, ["man_hours", "manHours", "man_hours_saved"], None
    )
    if has_value(man_hours_value):
        num = parse_number(man_hours_value, 0)
        return f"{num:,.0f} man hrs saved", "Man Hours"

    tat_value = first_value(
        item, ["tat_reduction", "tat", "tat_improvement"], None
    )
    if has_value(tat_value):
        num = parse_number(tat_value, 0)
        return f"{num:,.2f} hrs TAT reduction", "TAT Reduction"

    return "", ""
# ---------------------------------------------------------------------------
# Comprehensive field mapping
# ---------------------------------------------------------------------------

def get_field(item, field_names, default=None):
    """
    Get field value trying multiple possible names (handles various casing/spacing).
    field_names: list of possible field name variations
    """
    for name in field_names:
        if name in item and has_value(item[name]):
            return item[name]
    return default


def normalize_item(item):
    """
    Normalize a raw DB item to consistent schema with all fields populated.
    Handles all stream types (RPA, PowerApps, PowerAgents, AI, IBPS, DocuSign).
    """
    
    # Get sectionId / vertical
    section_id = get_field(
        item,
        ["sectionId", "section_id", "deliveryStream", "vertical", "stream"],
        "RPA"
    )
    if section_id:
        section_id = str(section_id).upper()
    
    # Normalize nexusId
    nexus_id = get_field(
        item,
        ["nexusId", "nexus_id", "NEXUS ID", "Nexus ID"],
        ""
    )
    
    # Normalize process name
    process_name = get_field(
        item,
        ["process_name", "processName",  "Process Name", "Process Name/Use Cases", "name", "Project"],
        "Untitled initiative"
    )
    
    # Status
    status = get_field(
        item,
        ["status", "Status"],
        ""
    )
    
    # Department
    department = get_field(
        item,
        ["department", "Department"],
        ""
    )
    
    # Division
    division = get_field(
        item,
        ["division", "Division"],
        ""
    )
    
    # Country
    country = get_field(
        item,
        ["country", "Country"],
        ""
    )
    
    # Problem statement
    problem_statement = get_field(
        item,
        ["problem_statement", "problemStatement",  "Problem Statement", "Problem Statement/Description"],
        ""
    )
    
    # Proposed solution
    proposed_solution = get_field(
        item,
        ["proposed_solution", "proposedSolution",  "Proposed Solution", "Solution Statements", "Solution Statement"],
        ""
    )
    
    # Man hours
    man_hours = parse_number(
        get_field(
            item,
            ["man_hours", "manHours",  "Man Hours", "Man Hours Saved"],
            0
        ),
        0
    )
    
    # Incremental hours
    incremental_hours = parse_number(
        get_field(
            item,
            ["incremental_hrs","incrementalHours",  "Incremental HRs", "Incremental hours"],
            ""
        ),
        0
    )
    
    # TAT reduction
    tat_reduction = parse_number(
        get_field(
            item,
            ["tat_reduction", "tatReduction",  "TAT Reduction (Specify Hours or Days)", "tat"],
            ""
        ),
        0
    )
    
    # Cost savings
    cost_savings = parse_number(
        get_field(
            item,
            ["cost_savings", "costSavings", "Cost Savings (KES)", "Cost Savings"],
            ""
        ),
        0
    )

    other_cost_savings = parse_number(
        get_field(
            item,
            ["other_cost_savings"]
        )
    )
    
    # Paper savings / Paper and print savings
    paper_savings = parse_number(
        get_field(
            item,
            ["paper_savings","paperSavings",  "Paper and Printing Cost Savings (KES)", "Total Paper and Printing Cost Savings (KES)"],
            ""
        ),
        0
    )
    
    # Qualitative benefits
    qual_value = get_field(
        item,
        ["qualitative_benefits","qualBenefits",  "qualitative", "Qualitative Benefits"],
        ""
    )
    if isinstance(qual_value, list):
        qual_text = " • ".join(str(x).strip() for x in qual_value if str(x).strip())
    else:
        qual_text = str(qual_value or "")
    
    quant_text, quant_type = pick_quant_benefit(item)

    # Target completion
    target_completion = normalize_date(
        get_field(
            item,
            ["target_completion","targetCompletion",  "Target Completion", "Target Completion Date", "Targeted Date"],
            ""
        )
    )
    
    # Process owner
    process_owner = get_field(
        item,
        ["process_owner", "processOwner", "Process Owner"],
        ""
    )
    
    # Benefits signed off
    benefits_signed = get_field(
        item,
        ["benefits_signof","benefitsSigned",  "Benefits Signed Off By", "Benefits Signed off by"],
        ""
    )
    
    # Developer
    developer = get_field(
        item,
        ["developer", "Developer"],
        ""
    )
    
    # Architect
    architect = get_field(
        item,
        ["architect", "Architect"],
        ""
    )
    
    # Analyst
    analyst = get_field(
        item,
        ["analyst", "Analyst"],
        ""
    )
    
    # BPM Owner (for IBPS/DocuSign)
    bpm_owner = get_field(
        item,
        ["bpm_owner","bpmOwner", "BPM Owner"],
        ""
    )
    
    # Comments
    comments = get_field(
        item,
        ["comments", "Comments"],
        ""
    )
    
    # AI-specific fields
    ai_type = get_field(
        item,
        ["type", "Type"],
        ""
    )
    
    vendor = get_field(
        item,
        ["vendor", "Vendor"],
        ""
    )
    
    ai_cluster = get_field(
        item,
        ["ai_cluster", "aiCluster", "AI Cluster", ],
        ""
    )
    benefits_validated = get_field(
        item,
        ["benefits_validated", "benefits_validatedby"]
    )
    
    benefits_approved = get_field(
        item,
        ["benefits_approved", "benefits_approvedby"]
    )

    # Return normalized item with ALL fields
    normalized = {
        "id": item.get("id", ""),
        "sectionId": section_id,
        "nexusId": nexus_id,
        "processName": process_name,
        "name": process_name,  # for landing page compatibility
        "status": status,
        "department": department,
        "division": division,
        "country": country,
        "problemStatement": problem_statement,
        "proposedSolution": proposed_solution,
        "solution": proposed_solution,
        "manHours": man_hours,
        "incrementalHours": incremental_hours,
        "tatReduction": tat_reduction,
        "tat": tat_reduction,  # for compatibility
        "costSavings": cost_savings,
        "totalCostSavings": cost_savings,
        "costSavingsDocusign": other_cost_savings,
        "paperSavings": paper_savings,
        "paperPrintSavings": paper_savings,  # for IBPS
        "quant": quant_text,
        "quantType": quant_type,
        "qualBenefits": qual_text,
        "qual": qual_text,  # for compatibility
        "targetCompletion": target_completion,
        "processOwner": process_owner,
        "benefitsSigned": benefits_signed,
        "benefitsSignoff": benefits_signed,  # variant
        "benefitsValidated": benefits_validated,
        "benefitsApproved": benefits_approved,
        "developer": developer,
        "architect": architect,
        "analyst": analyst,
        "bpmOwner": bpm_owner,
        "comments": comments,
        "type": ai_type,
        "vendor": vendor,
        "aiCluster": ai_cluster,
        "vertical": section_id.replace("_", " "),  # for display
    }
    
    return normalized


# ---------------------------------------------------------------------------
# Database query
# ---------------------------------------------------------------------------

def query_initiatives():
    from database import get_container

    container = get_container()
    partition_values = ["AI", "RPA", "POWERAPPS", "POWERAGENTS", "IBPS", "DOCUSIGN"]
    all_items = []

    for partition in partition_values:
        try:
            items = list(
                container.query_items(
                    query="SELECT * FROM c",
                    partition_key=partition,
                )
            )
            log.debug("Partition %s: fetched %d item(s)", partition, len(items))
            all_items.extend(items)
        except Exception:
            log.exception("Failed to query partition '%s' — skipping", partition)

    valid_items = [
    i for i in all_items
    if i and get_field(i, ["processName", "process_name", "Process Name", "Process Name/Use Cases", "name", "Project"])
    ]
    skipped = len(all_items) - len(valid_items)
    if skipped:
        log.warning("Skipped %d blank/incomplete record(s)", skipped)

    return [normalize_item(item) for item in valid_items]
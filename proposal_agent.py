#!/usr/bin/env python3
"""Investment Proposal Generator for Indian Mutual Fund Advisors.

Creates a client-ready markdown proposal using:
1) Risk-profiling questionnaire responses
2) Goal and investment amount
3) AMFI mutual fund scheme data (online with offline fallback)
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

AMFI_NAV_URLS = [
    "https://www.amfiindia.com/spages/NAVAll.txt",
    "https://portal.amfiindia.com/spages/NAVAll.txt",
]
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ProposalAgent/1.0)",
    "Accept": "text/plain,*/*;q=0.8",
}
LOCAL_AMFI_FALLBACK = Path("data/amfi_sample_nav.txt")


@dataclass
class ClientProfile:
    email_address: str
    name: str
    date_of_birth: str
    whatsapp_no: str
    primary_investment_objective: str
    expected_investment_time_horizon: str
    expected_returns: str
    drawdown_reaction: str
    equity_exposure: str
    investable_income_pct: str
    active_investing_duration: str
    income_stability: str
    emergency_fund_status: str
    loan_obligations: str
    investor_statement: str
    most_important_goal: str
    client_declaration: str
    has_health_insurance: str
    has_term_insurance: str
    has_personal_accidental_insurance: str
    monthly_investment_amount_inr: float


def _prompt(label: str) -> str:
    value = input(f"{label}: ").strip()
    while not value:
        value = input(f"{label} (required): ").strip()
    return value


def _prompt_float(label: str) -> float:
    while True:
        raw = _prompt(label).replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            print("Please enter a valid number (example: 25000 or 25000.50).")
            continue
        if value <= 0:
            print("Please enter an amount greater than 0.")
            continue
        return value


def capture_client_profile() -> ClientProfile:
    print("\n=== Client Risk Profiling Intake ===\n")
    return ClientProfile(
        email_address=_prompt("Email Address"),
        name=_prompt("Name"),
        date_of_birth=_prompt("Date of Birth (YYYY-MM-DD)"),
        whatsapp_no=_prompt("Whatsapp no"),
        primary_investment_objective=_prompt("What is your primary investment objective?"),
        expected_investment_time_horizon=_prompt("What is your expected investment time horizon?"),
        expected_returns=_prompt("What level of returns do you expect from your investments?"),
        drawdown_reaction=_prompt("If your portfolio falls by 15%–20% in the short term, what would you do?"),
        equity_exposure=_prompt("How much of your total savings is invested in equity (mutual funds or stocks)?"),
        investable_income_pct=_prompt("What percentage of your income can you invest comfortably?"),
        active_investing_duration=_prompt("For how long have you been actively investing?"),
        income_stability=_prompt("How stable is your primary source of income?"),
        emergency_fund_status=_prompt("Do you have an emergency fund covering at least 6 months of expenses?"),
        loan_obligations=_prompt("What best describes your current loan obligations?"),
        investor_statement=_prompt("Which statement best describes you as an investor?"),
        most_important_goal=_prompt("Which goal is most important for you right now?"),
        client_declaration=_prompt("Client Declaration"),
        has_health_insurance=_prompt("Do you have a Health Insurance (Yes/No)"),
        has_term_insurance=_prompt("Do you have a Term Insurance (Yes/No)"),
        has_personal_accidental_insurance=_prompt("Do you have a Accidental personal Insurance (Yes/No)"),
        monthly_investment_amount_inr=_prompt_float("Monthly SIP investment amount (INR)"),
    )


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def score_risk(profile: ClientProfile) -> Tuple[int, str]:
    score = 0

    horizon = _normalize(profile.expected_investment_time_horizon)
    if any(k in horizon for k in ["10", "15", "long", "retirement", ">=10"]):
        score += 3
    elif any(k in horizon for k in ["5", "7", "8"]):
        score += 2
    else:
        score += 1

    drawdown = _normalize(profile.drawdown_reaction)
    if any(k in drawdown for k in ["buy", "invest more", "hold"]):
        score += 3
    elif "wait" in drawdown or "partial" in drawdown:
        score += 2
    else:
        score += 1

    equity = _normalize(profile.equity_exposure)
    if any(k in equity for k in ["50", "60", "70", "80", "90", "100", "majority"]):
        score += 3
    elif any(k in equity for k in ["20", "30", "40"]):
        score += 2
    else:
        score += 1

    experience = _normalize(profile.active_investing_duration)
    if any(k in experience for k in ["10", "7", "8", "9", "experienced"]):
        score += 3
    elif any(k in experience for k in ["3", "4", "5", "6"]):
        score += 2
    else:
        score += 1

    stability = _normalize(profile.income_stability)
    if any(k in stability for k in ["very stable", "government", "tenured", "secure"]):
        score += 3
    elif "moderate" in stability or "mostly stable" in stability:
        score += 2
    else:
        score += 1

    emergency = _normalize(profile.emergency_fund_status)
    if "yes" in emergency:
        score += 2

    loan = _normalize(profile.loan_obligations)
    if any(k in loan for k in ["none", "minimal"]):
        score += 2
    elif any(k in loan for k in ["manageable", "moderate"]):
        score += 1

    if score >= 17:
        band = "Aggressive"
    elif score >= 12:
        band = "Moderate"
    else:
        band = "Conservative"

    return score, band


def _parse_amfi_nav_text(text: str) -> List[Dict[str, str]]:
    rows = []
    reader = csv.reader(text.splitlines(), delimiter=";")
    current_category = ""

    for cols in reader:
        if len(cols) == 1:
            candidate = cols[0].strip()
            if candidate and not candidate.startswith("Open Ended") and not candidate.startswith("Close Ended"):
                current_category = candidate
            continue

        if len(cols) < 6:
            continue

        scheme_name = cols[3].strip()
        nav = cols[4].strip()
        date = cols[5].strip()
        if not scheme_name or not nav or not date:
            continue
        if "direct" not in scheme_name.lower() or "growth" not in scheme_name.lower():
            continue

        rows.append(
            {
                "scheme_code": cols[0].strip(),
                "isin_div_payout": cols[1].strip(),
                "isin_div_reinvest": cols[2].strip(),
                "scheme_name": scheme_name,
                "nav": nav,
                "date": date,
                "category": current_category or "Unclassified",
            }
        )

    return rows


def fetch_amfi_nav_data() -> Tuple[List[Dict[str, str]], str]:
    errors: List[str] = []
    for url in AMFI_NAV_URLS:
        request = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                text = response.read().decode("utf-8", errors="ignore")
            parsed = _parse_amfi_nav_text(text)
            if parsed:
                return parsed, f"Live AMFI feed ({url})"
            errors.append(f"{url}: received empty/invalid data")
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            errors.append(f"{url}: {exc}")

    if LOCAL_AMFI_FALLBACK.exists():
        parsed = _parse_amfi_nav_text(LOCAL_AMFI_FALLBACK.read_text(encoding="utf-8"))
        if parsed:
            return parsed, f"Local fallback snapshot ({LOCAL_AMFI_FALLBACK})"

    raise RuntimeError("AMFI fetch failed. " + " | ".join(errors))


def pick_recommended_funds(risk_band: str, nav_data: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    category_map = {
        "Conservative": ["Liquid", "Ultra Short", "Corporate Bond", "Banking and PSU", "Short Duration", "Hybrid Debt"],
        "Moderate": ["Large Cap", "Flexi Cap", "Balanced Advantage", "Aggressive Hybrid", "Corporate Bond", "Multi Asset"],
        "Aggressive": ["Large Cap", "Flexi Cap", "Mid Cap", "Small Cap", "Index", "ELSS"],
    }

    selected_keywords = category_map[risk_band]
    selected: Dict[str, List[Dict[str, str]]] = {k: [] for k in selected_keywords}

    for row in nav_data:
        scheme_name = row["scheme_name"].lower()
        category = row["category"].lower()
        for keyword in selected_keywords:
            kw = keyword.lower()
            if kw in scheme_name or kw in category:
                if len(selected[keyword]) < 2:
                    selected[keyword].append(row)
                break

    return {k: v for k, v in selected.items() if v}


def sip_allocation(risk_band: str, monthly_amount: float) -> Dict[str, float]:
    weights = {
        "Conservative": {"Debt / Liquid": 0.55, "Hybrid": 0.30, "Equity": 0.15},
        "Moderate": {"Debt": 0.30, "Hybrid": 0.30, "Equity": 0.40},
        "Aggressive": {
            "Large & Flexi Cap": 0.40,
            "Mid & Small Cap": 0.35,
            "Thematic / ELSS / Index": 0.15,
            "Debt / Liquid": 0.10,
        },
    }
    return {bucket: round(monthly_amount * wt, 2) for bucket, wt in weights[risk_band].items()}


def proposal_markdown(
    profile: ClientProfile,
    risk_score: int,
    risk_band: str,
    allocations: Dict[str, float],
    funds: Dict[str, List[Dict[str, str]]],
    data_source_note: str,
) -> str:
    today = dt.date.today().isoformat()
    age = "N/A"
    try:
        dob = dt.date.fromisoformat(profile.date_of_birth)
        age = str(today_as_age(dob))
    except ValueError:
        pass

    insurance_gaps = []
    if _normalize(profile.has_health_insurance) != "yes":
        insurance_gaps.append("Health Insurance")
    if _normalize(profile.has_term_insurance) != "yes":
        insurance_gaps.append("Term Insurance")
    if _normalize(profile.has_personal_accidental_insurance) != "yes":
        insurance_gaps.append("Personal Accidental Insurance")
    insurance_note = "All key insurances in place." if not insurance_gaps else f"Protection gap identified: {', '.join(insurance_gaps)}"

    lines = [
        f"# Mutual Fund Investment Proposal - {profile.name}",
        "",
        f"**Proposal Date:** {today}",
        f"**Client Email:** {profile.email_address}",
        f"**WhatsApp:** {profile.whatsapp_no}",
        f"**Age:** {age}",
        f"**Primary Goal:** {profile.most_important_goal}",
        "",
        "## 1) Investor Snapshot",
        f"- Primary investment objective: {profile.primary_investment_objective}",
        f"- Investment horizon: {profile.expected_investment_time_horizon}",
        f"- Return expectation: {profile.expected_returns}",
        f"- Current investable surplus: {profile.investable_income_pct}",
        f"- Income stability: {profile.income_stability}",
        f"- Investor style statement: {profile.investor_statement}",
        "",
        "## 2) Risk Profiling Outcome",
        f"- Risk score: **{risk_score}**",
        f"- Risk band: **{risk_band}**",
        f"- Behaviour under volatility: {profile.drawdown_reaction}",
        f"- Equity exposure today: {profile.equity_exposure}",
        "",
        "## 3) Suggested Monthly SIP Allocation",
        f"- Total monthly SIP: **₹{profile.monthly_investment_amount_inr:,.2f}**",
    ]
    for bucket, value in allocations.items():
        lines.append(f"- {bucket}: **₹{value:,.2f}**")

    lines.extend(["", "## 4) AMFI Data-backed Scheme Suggestions", f"_Source: {data_source_note} (Direct Growth plans filtered)._", ""])

    if not funds:
        lines.append("No schemes matched filter criteria from current AMFI dataset. Re-run later or refine category matching.")
    else:
        for category, schemes in funds.items():
            lines.append(f"### {category}")
            for s in schemes:
                lines.append(f"- **{s['scheme_name']}** | NAV: ₹{s['nav']} | Date: {s['date']} | Scheme Code: {s['scheme_code']}")
            lines.append("")

    lines.extend(
        [
            "## 5) Protection & Readiness Check",
            f"- Emergency fund status: {profile.emergency_fund_status}",
            f"- Loan obligations: {profile.loan_obligations}",
            f"- Insurance observation: {insurance_note}",
            "",
            "## 6) Advisor Notes & Declaration",
            f"- Client declaration: {profile.client_declaration}",
            "- This proposal is for educational and planning purposes, not a return guarantee.",
            "- Final fund selection should consider suitability, taxation, and periodic review.",
        ]
    )

    return "\n".join(lines) + "\n"


def today_as_age(dob: dt.date) -> int:
    today = dt.date.today()
    years = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        years -= 1
    return years


def load_profile_from_json(path: Path) -> ClientProfile:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return ClientProfile(**data)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate advisor-grade mutual fund proposal for Indian retail clients.")
    parser.add_argument("--input-json", type=Path, help="Path to JSON file matching ClientProfile fields.")
    parser.add_argument("--output", type=Path, default=Path("proposal.md"), help="Output markdown file path.")
    args = parser.parse_args()

    try:
        profile = load_profile_from_json(args.input_json) if args.input_json else capture_client_profile()
    except Exception as exc:
        print(f"Error loading client profile: {exc}", file=sys.stderr)
        return 1

    risk_score, risk_band = score_risk(profile)

    try:
        nav_data, source_note = fetch_amfi_nav_data()
    except Exception as exc:
        print(f"Warning: failed to fetch AMFI data and fallback snapshot: {exc}", file=sys.stderr)
        nav_data, source_note = [], "Unavailable in current environment"

    recommendations = pick_recommended_funds(risk_band, nav_data) if nav_data else {}
    allocations = sip_allocation(risk_band, profile.monthly_investment_amount_inr)

    content = proposal_markdown(profile, risk_score, risk_band, allocations, recommendations, source_note)
    args.output.write_text(content, encoding="utf-8")
    print(f"Proposal generated at: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

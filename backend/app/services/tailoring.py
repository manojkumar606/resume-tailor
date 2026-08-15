"""Tailoring: rewrite a resume for a specific job and score the match."""

from dataclasses import dataclass
from typing import Any

from app.services.llm import LLMError, LLMProvider

# Cap what we send. Long postings are mostly boilerplate (benefits, EEO
# statements) and the tail rarely changes the rewrite, but it does cost tokens.
MAX_JOB_DESCRIPTION_CHARS = 8000
MAX_RESUME_CHARS = 20000

TAILOR_SYSTEM = """You are an expert resume writer and career coach.

You rewrite a candidate's resume to maximise relevance for one specific job.

Hard rules:
- NEVER invent experience, employers, dates, degrees, certifications, or skills
  the candidate does not already have. Rephrasing is allowed; fabrication is not.
- Keep the candidate's real employment history and dates exactly as given.
- Preserve the overall section structure of the original resume.
- Naturally incorporate genuine keywords from the job description where the
  candidate's real experience supports them.
- Sharpen bullets with stronger verbs and concrete outcomes, but only quantify
  where the original already contains a number.
- Keep the tone professional and concise.

When revising a previous attempt, treat the candidate's complaints as
instructions and address every one of them. The rules above still hold — a
request to sound stronger is not permission to invent anything.

Return ONLY a JSON object with exactly these keys:
{
  "tailored_resume": "the full rewritten resume as plain text, one line per
                      line of the document, using '- ' to start bullet points
                      and ALL CAPS lines for section headings",
  "match_score": <integer 0-100, how well the candidate genuinely fits this
                  role BEFORE tailoring — be honest, do not inflate>,
  "missing_keywords": ["requirements from the posting the candidate genuinely
                       does not meet — do not paper over these"],
  "changes": ["short bullet describing each significant edit you made"]
}

Do not wrap the JSON in markdown fences. Do not add commentary."""


@dataclass
class TailoringResult:
    tailored_text: str
    match_score: float | None
    missing_keywords: list[str]
    changes: list[str]


# A revision carries the previous attempt as well, so the cap matters more here.
MAX_PREVIOUS_ATTEMPT_CHARS = 20000


def build_prompt(
    resume_text: str,
    job_title: str,
    company: str,
    description: str,
    previous_attempt: str | None = None,
    critique: str | None = None,
) -> str:
    parts = [
        f"JOB TITLE: {job_title}",
        f"COMPANY: {company}",
        f"\nJOB DESCRIPTION:\n{description[:MAX_JOB_DESCRIPTION_CHARS]}",
        f"\nCANDIDATE'S CURRENT RESUME:\n{resume_text[:MAX_RESUME_CHARS]}",
    ]

    if previous_attempt and critique:
        parts.append(
            f"\nYOUR PREVIOUS ATTEMPT:\n{previous_attempt[:MAX_PREVIOUS_ATTEMPT_CHARS]}"
        )
        parts.append(f"\nWHAT THE CANDIDATE SAYS IS WRONG WITH IT:\n{critique}")
        # Restated after the critique, not only in the system prompt: the
        # complaints are user-supplied text, and "make me sound stronger" must
        # not read as licence to invent.
        parts.append(
            "\nProduce a new version that addresses every point above. Do not "
            "add any experience, skill or qualification the candidate does not "
            "already have."
        )

    return "\n".join(parts)


def _coerce_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()][:20]


def _coerce_score(value: Any) -> float | None:
    """Clamp the model's score into 0-100, or drop it if it isn't a number.

    A wrong score is worse than no score, since the UI presents it as fact.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if score != score:  # NaN
        return None
    return max(0.0, min(100.0, score))


def parse_result(payload: dict[str, Any]) -> TailoringResult:
    text = payload.get("tailored_resume")
    if not isinstance(text, str) or not text.strip():
        raise LLMError("The model response did not contain a tailored resume")

    return TailoringResult(
        tailored_text=text.strip(),
        match_score=_coerce_score(payload.get("match_score")),
        missing_keywords=_coerce_str_list(payload.get("missing_keywords")),
        changes=_coerce_str_list(payload.get("changes")),
    )


def build_critique(feedback: list[str], notes: str | None) -> str | None:
    """Turn the chips and free text into one instruction block.

    Chips exist because a blank "what's wrong?" box makes people freeze, and
    because they give the model unambiguous, consistent wording to act on.
    """
    lines = [f"- {item}" for item in feedback]
    if notes and notes.strip():
        lines.append(f"- In their own words: {notes.strip()}")
    return "\n".join(lines) if lines else None


def tailor(
    provider: LLMProvider,
    *,
    resume_text: str,
    job_title: str,
    company: str,
    description: str,
    previous_attempt: str | None = None,
    critique: str | None = None,
) -> TailoringResult:
    prompt = build_prompt(
        resume_text, job_title, company, description, previous_attempt, critique
    )
    payload = provider.generate_json(system=TAILOR_SYSTEM, prompt=prompt)
    return parse_result(payload)

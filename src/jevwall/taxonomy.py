"""The technique matrix: tactics (columns) and techniques (cells), with the criteria sent to Jev."""
# ruff: noqa: E501

from dataclasses import asdict, dataclass

NONE_ID = "none"
# The version of MITRE's published ATLAS data the references below were checked against.
ATLAS_VERSION = "5.6.0"
NONE_CRITERIA = (
    "An ordinary request with no attempt to manipulate, override, or probe the assistant."
)


@dataclass(frozen=True)
class Technique:
    id: str
    name: str
    criteria: str


@dataclass(frozen=True)
class Tactic:
    id: str
    name: str
    techniques: list[Technique]
    # The closest MITRE ATLAS technique(s), id -> name. This matrix is a custom taxonomy, not an
    # official ATLAS mapping; the references are a signpost for anyone who knows ATLAS.
    atlas: dict[str, str]


TACTICS: list[Tactic] = [
    Tactic(
        "override",
        "Instruction Override",
        [
            Technique(
                "ignore_previous",
                "Ignore previous",
                "Tells the assistant to ignore, forget, or disregard its earlier instructions.",
            ),
            Technique(
                "new_system_prompt",
                "Fake system prompt",
                "Supplies text formatted as a new system message or developer instruction.",
            ),
            Technique(
                "priority_claim",
                "Priority claim",
                "Claims its instructions outrank or supersede the assistant's rules.",
            ),
            Technique(
                "task_hijack",
                "Task hijack",
                "Abandons the stated task and substitutes a different one mid-prompt.",
            ),
            Technique(
                "fake_completion",
                "Fake completion",
                "Pretends the original task is already finished so that new instructions follow.",
            ),
        ],
        {"AML.T0051.000": "LLM Prompt Injection: Direct"},
    ),
    Tactic(
        "persona",
        "Persona & Role-play",
        [
            Technique(
                "dan_persona",
                "DAN-style persona",
                "Asks the assistant to become a named unrestricted alter ego such as DAN.",
            ),
            Technique(
                "fiction_frame",
                "Fiction frame",
                "Wraps a harmful request inside a story, script, or game.",
            ),
            Technique(
                "dev_mode",
                "Developer mode",
                "Claims a debug, developer, or test mode in which rules are off.",
            ),
            Technique(
                "opposite_mode",
                "Opposite mode",
                "Asks for the opposite of the normal safe behaviour, or for two contrasting answers.",
            ),
            Technique(
                "character_lock",
                "Character lock",
                "Demands the assistant stay in character no matter what and never refuse.",
            ),
        ],
        {"AML.T0054": "LLM Jailbreak"},
    ),
    Tactic(
        "obfuscation",
        "Obfuscation",
        [
            Technique(
                "encoding",
                "Encoding",
                "Hides the request in base64, hex, rot13, leetspeak, or another encoding.",
            ),
            Technique(
                "language_switch",
                "Language switch",
                "Switches to another language to slip past filters.",
            ),
            Technique(
                "payload_split",
                "Payload splitting",
                "Splits a harmful request into harmless-looking pieces to be joined.",
            ),
            Technique(
                "token_smuggle",
                "Token smuggling",
                "Uses odd spacing, homoglyphs, or invisible characters to disguise words.",
            ),
            Technique(
                "code_wrap",
                "Code wrapper",
                "Buries the instruction inside code, a function, or a variable to be evaluated.",
            ),
        ],
        {"AML.T0068": "LLM Prompt Obfuscation"},
    ),
    Tactic(
        "extraction",
        "Extraction",
        [
            Technique(
                "prompt_leak",
                "System prompt leak",
                "Asks the assistant to reveal, repeat, or summarise its hidden instructions.",
            ),
            Technique(
                "secret_probe",
                "Secret probing",
                "Tries to extract a password, key, or other secret the assistant holds.",
            ),
            Technique(
                "context_dump",
                "Context dump",
                "Asks for everything above, the full conversation, or internal context verbatim.",
            ),
            Technique(
                "training_probe",
                "Training data probe",
                "Tries to make the assistant regurgitate training data or private records.",
            ),
        ],
        {"AML.T0056": "Extract LLM System Prompt", "AML.T0057": "LLM Data Leakage"},
    ),
    Tactic(
        "pressure",
        "Social Pressure",
        [
            Technique(
                "authority_claim",
                "Authority claim",
                "Claims to be the developer, an admin, or law enforcement to gain compliance.",
            ),
            Technique(
                "urgency",
                "Urgency or threat",
                "Uses emergencies, threats, or penalties to force compliance.",
            ),
            Technique(
                "emotional_appeal",
                "Emotional appeal",
                "Uses guilt, sympathy, or a sad story to justify a harmful request.",
            ),
            Technique(
                "hypothetical",
                "Hypothetical framing",
                "Frames the request as purely hypothetical, academic, or for research.",
            ),
            Technique(
                "reward_game",
                "Reward game",
                "Offers points, tokens, or rewards for answering without refusing.",
            ),
        ],
        {"AML.T0054": "LLM Jailbreak"},
    ),
    Tactic(
        "indirect",
        "Indirect & Tooling",
        [
            Technique(
                "embedded_instruction",
                "Embedded instruction",
                "Hides instructions inside a document, email, or web page the assistant is asked to process.",
            ),
            Technique(
                "tool_abuse",
                "Tool abuse",
                "Tries to make the assistant call tools, send data, or act outside the user's task.",
            ),
            Technique(
                "output_format_trap",
                "Output format trap",
                "Forces an output format or prefix that makes refusal impossible.",
            ),
            Technique(
                "chained_request",
                "Chained request",
                "Builds up a harmful result through a sequence of individually harmless steps.",
            ),
        ],
        {
            "AML.T0051.001": "LLM Prompt Injection: Indirect",
            "AML.T0053": "AI Agent Tool Invocation",
        },
    ),
]


def choice_criteria() -> dict[str, str]:
    criteria = {t.id: t.criteria for tactic in TACTICS for t in tactic.techniques}
    criteria[NONE_ID] = NONE_CRITERIA
    return criteria


def as_json() -> list[dict]:
    return [asdict(tactic) for tactic in TACTICS]

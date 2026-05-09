# CrewAI Integration

`GroundlensTool` enables CrewAI agents to verify their own outputs for hallucination risk before presenting results to users or other agents.

## Installation

```bash
pip install "groundlens[crewai]"
```

## Quick Start

```python
from groundlens.integrations.crewai import GroundlensTool

tool = GroundlensTool()

# Verify a response
result = tool._run(
    question="What is the recommended dosage for ibuprofen?",
    response="The recommended dosage is 200-400mg every 4-6 hours.",
    context="Ibuprofen: 200-400mg PO every 4-6 hours. Max 1200mg/day OTC.",
)
print(result)
```

**Output:**

```text
Groundlens Verification Result
----------------------------
Method: SGI
Score: 1.234 (normalized: 0.614)
Status: PASS
Explanation: SGI=1.234 -- strong context engagement (pass)
```

## Configuration

```python
tool = GroundlensTool(
    name="groundlens_verify",           # Tool name visible to the agent
    description="Verify a response...",  # Custom description
    groundlens_model="all-MiniLM-L6-v2",  # Embedding model
)
```

| Parameter | Default | Description |
|---|---|---|
| `name` | `"groundlens_verify"` | Tool name for agent tool selection |
| `description` | (built-in) | Description shown to the agent |
| `groundlens_model` | `"all-MiniLM-L6-v2"` | Sentence-transformer for scoring |

## Using in a CrewAI Agent

```python
from crewai import Agent, Task, Crew
from groundlens.integrations.crewai import GroundlensTool

# Create the verification tool
verify_tool = GroundlensTool()

# Create an agent that uses groundlens for self-verification
researcher = Agent(
    role="Research Analyst",
    goal="Provide accurate, verified research summaries",
    tools=[verify_tool],
    backstory="You are a meticulous researcher who always verifies your findings.",
)

# The agent can call groundlens_verify to check its own outputs
task = Task(
    description="Research the effects of caffeine on sleep quality. Verify your findings.",
    agent=researcher,
    expected_output="A verified summary of caffeine's effects on sleep.",
)

crew = Crew(agents=[researcher], tasks=[task])
result = crew.kickoff()
```

## Tool Input/Output

### Input

The `_run` method accepts:

| Parameter | Required | Description |
|---|---|---|
| `question` | Yes | The original question or prompt |
| `response` | Yes | The response to verify |
| `context` | No | Source context (enables SGI when provided) |

### Output

Returns a formatted string containing:

- **Method**: SGI or DGI
- **Score**: Raw and normalized values
- **Status**: PASS or FLAGGED
- **Explanation**: Human-readable interpretation
- **Recommendation** (if flagged): Suggestion to revise with verified sources

## Agent Self-Verification Pattern

The most powerful use of GroundlensTool is **agent self-verification**: the agent generates a response, verifies it with groundlens, and revises if flagged.

```python
researcher = Agent(
    role="Medical Information Specialist",
    goal="Provide accurate medical information, always verified",
    tools=[GroundlensTool()],
    backstory=(
        "You are a medical information specialist. Before presenting any answer, "
        "you MUST use the groundlens_verify tool to check your response. If flagged, "
        "revise your answer and verify again."
    ),
)
```

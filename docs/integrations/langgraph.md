# LangGraph Integration

groundlens provides a LangGraph-aware callback handler that automatically scores every LLM call in an agentic pipeline, builds a structured execution trace, and generates self-contained HTML triage reports.

## Installation

```bash
pip install "groundlens[langgraph]"
```

This installs `langgraph` and `langchain-core`.

## GroundlensLangGraphCallback

The callback intercepts every LLM call within a LangGraph execution, evaluates each response with groundlens, and accumulates the results into a structured `AgentTrace`.

### Basic Usage

```python
from langgraph.graph import StateGraph
from groundlens.integrations.langgraph import GroundlensLangGraphCallback

gl = GroundlensLangGraphCallback()

# Pass the callback in the LangGraph config
result = app.invoke(
    {"question": "What is the capital of France?"},
    config={"callbacks": [gl]},
)

# Get the execution trace
trace = gl.get_trace()
print(trace.summary())
```

Output:

```
Agent completed: 3 steps (523ms)
✓ 2 trusted  ⚠ 0 review  ✗ 1 flagged
Flagged: fact_check (DGI=0.180)
```

### Configuration

```python
gl = GroundlensLangGraphCallback(
    groundlens_model="all-MiniLM-L6-v2",  # Embedding model
    context_key="context",                  # Metadata key for explicit context
)
```

| Parameter | Default | Description |
|---|---|---|
| `groundlens_model` | `"all-MiniLM-L6-v2"` | Sentence-transformer model for scoring |
| `context_key` | `"context"` | Metadata key for explicit context override |

### Auto Context Detection

The callback automatically detects grounding context:

1. **Explicit context** — If metadata contains the `context_key`, that value is used.
2. **Tool output** — If a tool call produced output before the LLM call, the tool output becomes the grounding context (SGI scoring).
3. **No context** — When neither is available, DGI (ungrounded) scoring is applied.

This means tool-augmented nodes automatically get SGI scoring, while reasoning nodes that generate without retrieval get DGI scoring — no configuration required.

### Graph Node Tracking

The callback tracks which LangGraph node produced each LLM call. Node names are resolved from:

1. The `langgraph_node` key in chain metadata.
2. The chain's serialized `name` field (excluding internal wrappers like `RunnableSequence`).

This enables per-node triage in the execution trace.

### Resetting State

To reuse the same callback across multiple invocations, call `reset()` between runs:

```python
gl = GroundlensLangGraphCallback()

result1 = app.invoke(input1, config={"callbacks": [gl]})
trace1 = gl.get_trace()

gl.reset()

result2 = app.invoke(input2, config={"callbacks": [gl]})
trace2 = gl.get_trace()
```

## AgentTrace

The `AgentTrace` object accumulates all evaluated steps and provides aggregate statistics, summaries, and export methods.

### Properties

| Property | Type | Description |
|---|---|---|
| `steps` | `list[AgentStep]` | Ordered list of evaluated steps |
| `total_steps` | `int` | Total number of evaluated steps |
| `flagged_steps` | `int` | Steps triaged as flagged |
| `review_steps` | `int` | Steps triaged as needing review |
| `trusted_steps` | `int` | Steps triaged as trusted |
| `total_duration_ms` | `float` | Total LLM call time in milliseconds |

### Triage Summary

```python
trace = gl.get_trace()
print(trace.summary())
```

The summary shows step counts by triage category and lists any flagged or review steps with their node name and score.

### Triage Loop

Iterate over steps to build custom handling logic:

```python
trace = gl.get_trace()

for step in trace.steps:
    if step.triage == "flagged":
        print(f"⚠ {step.node_name}: {step.score.explanation}")
    elif step.triage == "review":
        print(f"? {step.node_name}: needs human review")
    else:
        print(f"✓ {step.node_name}: trusted")
```

### JSON Export

```python
# As a Python dict
data = trace.to_dict()

# As a JSON string
json_str = trace.to_json(indent=2)
```

### HTML Report

Generate a self-contained HTML triage report:

```python
# Write to file
trace.to_html("report.html")

# Or get the HTML string
html = trace.to_html()
```

The HTML report includes a visual summary of all steps with color-coded triage status, scores, timing, and full input/output text.

## AgentStep

Each step in the trace is an `AgentStep` dataclass with the following fields:

| Field | Type | Description |
|---|---|---|
| `node_name` | `str` | LangGraph node that produced this LLM call |
| `step_index` | `int` | Execution order (0-based) |
| `input_text` | `str` | Prompt sent to the LLM |
| `output_text` | `str` | LLM response text |
| `context` | `str \| None` | Grounding context (tool output), or `None` for DGI |
| `score` | `GroundlensScore` | The groundlens evaluation result |
| `triage` | `str` | `"trusted"`, `"review"`, or `"flagged"` |
| `method` | `str` | `"sgi"` or `"dgi"` |
| `duration_ms` | `float` | LLM call latency in milliseconds |

## Triage Classification

Each step is classified into one of three triage categories:

| Category | Condition | Meaning |
|---|---|---|
| **trusted** | `normalized >= 0.6` and not flagged | Response is well-grounded |
| **review** | `normalized < 0.6` and not flagged | Low confidence — human review recommended |
| **flagged** | `score.flagged == True` | Likely hallucination detected |

## Logging

The callback uses Python's `logging` module under the `groundlens.integrations.langgraph.callback` logger:

- **WARNING** — Flagged responses (likely hallucinations)
- **INFO** — Passing responses
- **DEBUG** — Lifecycle events (chain start/end, tool start/end, LLM start)
- **ERROR** — Chain, tool, or LLM errors

```python
import logging
logging.basicConfig(level=logging.INFO)

gl = GroundlensLangGraphCallback()
# Now groundlens callback events appear in logs
```

## Complete Example

```python
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from groundlens.integrations.langgraph import GroundlensLangGraphCallback

# Build your LangGraph agent
builder = StateGraph(dict)

def research(state):
    llm = ChatOpenAI()
    result = llm.invoke(state["question"])
    return {"research": result.content}

def synthesize(state):
    llm = ChatOpenAI()
    result = llm.invoke(f"Summarize: {state['research']}")
    return {"answer": result.content}

builder.add_node("research", research)
builder.add_node("synthesize", synthesize)
builder.set_entry_point("research")
builder.add_edge("research", "synthesize")
builder.add_edge("synthesize", END)
app = builder.compile()

# Run with groundlens monitoring
gl = GroundlensLangGraphCallback()
result = app.invoke(
    {"question": "What are the latest advances in quantum computing?"},
    config={"callbacks": [gl]},
)

# Inspect the trace
trace = gl.get_trace()
print(trace.summary())

# Export report
trace.to_html("agent_report.html")

# Programmatic triage
for step in trace.steps:
    if step.triage == "flagged":
        print(f"Node '{step.node_name}' flagged: {step.score.explanation}")
```

## Why This Matters for Agentic AI

Multi-step agents make grounding harder to trace because errors compound across nodes. A hallucinated fact from an early reasoning step can propagate through tool calls and synthesis, producing a final answer that *looks* well-supported but rests on fabricated premises.

groundlens addresses this by scoring each LLM call independently at the node level. The triage trace shows exactly *where* in the pipeline confidence dropped, enabling targeted human review instead of blanket distrust of the entire output.

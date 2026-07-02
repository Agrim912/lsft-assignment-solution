# DESIGN.md (template — rename to DESIGN.md and fill in, max ~1 page)

## Architecture
_One paragraph + a small diagram. What are the agents/components, and what does each own?_

## Agent topology and why
_Why this number of agents? What would collapse to one? Why isn't there a redundant agent
that could do the same job as another?_

## How I handled each hard problem
- **Orchestration / ordering:** 
- **Tool ambiguity (current_budget vs planner_budget; list vs details):** 
- **Token optimisation (the 19MB list, referencePoint, response curves):** 
- **Latency / fewer LLM hops:** 
- **Zero hallucination (g07, g08, g10):** 
- **Grounding (no glossary tool; how you map terms→fields + spot ambiguity; g09):** 
- **Param correctness / recovery (camelCase):** 
- **Harness improvements:** 

## Trade-offs and what I cut
_What did you deliberately not do, and why? What would you do with another day?_

## Results
_Paste your harness output (structural pass count, total hops, total tokens)._

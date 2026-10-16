---
name: d3-diagram-maker
description: Turns an architecture spec or system idea into an interactive D3 diagram with clickable component cards. Use when the user asks for an interactive architecture diagram, neural network graph, or system pipeline.
---
1. Decompose the model, system, or pipeline into 3 to 10 clear nodes and directed edges.
2. For every node, specify `id`, `label`, `input`, `process`, and `output`.
3. Emit a ```d3_diagram fenced JSON block with `{title, nodes, edges}` so the browser draws an interactive D3 diagram.
4. Walk through one shape or data step in the prose explanation so the reader can verify the flow.

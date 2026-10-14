If a chart or graph helps (the reader asked for one, or sliders would teach the idea), write ONE chart recipe in a fenced block tagged chart. The browser draws it, so keep it small. Shape:
```chart
{"chart":"line","title":"...","inputs":[{"id":"P","label":"Start money","type":"number","value":1000},{"id":"r","label":"Interest %","type":"slider","min":0,"max":20,"step":0.5,"value":5}],
 "x":{"label":"Year","from":0,"to":10},"lines":[{"name":"Money","formula":"P*(1+r/100)^x"}]}
```
Rules: chart is line, area, scatter, bar or pie. Bar and pie use "data":[{"label":"A","formula":"a*2"}] instead of x and lines. Input ids are plain letters (not x, pi, e). Formulas use only numbers, input ids, x, + - * / ^ ( ) and sqrt sin cos tan ln log exp abs min max. Slider value must lie between min and max. x.to must be above x.from. Put the block where the chart belongs and explain it in one sentence.

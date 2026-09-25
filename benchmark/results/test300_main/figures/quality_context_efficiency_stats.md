# Quality vs. Context Efficiency Stats

- Primary method: JumpStarter-Shallow
- Primary study quality: 4.270 [4.223, 4.316]
- Primary input context tokens: 19158.120
- Primary selected context tokens: 268.493
- Versus no-selection baseline: +0.188 quality with 28.9% fewer input context tokens.
- Versus JumpStarter-Recursive: matched delta +0.073 [0.017, 0.130] for Shallow over Recursive.
- Versus random context selection: matched delta +0.128 [0.069, 0.187] for Shallow over random selection.

| Method | Family | n | Study quality | 95% CI | Input context tokens | Selected ctx tokens | Output words | Matched delta vs Shallow | 95% CI | W/T/L |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| JumpStarter-Shallow | Primary method | 300 | 4.270 | [4.223, 4.316] | 19158.120 | 268.493 | 1086.617 | -- | -- | -- |
| JumpStarter-Recursive | JumpStarter variants | 300 | 4.197 | [4.149, 4.244] | 24345.377 | 266.870 | 1077.763 | +0.073 | [0.017, 0.130] | 147/29/124 |
| No elicitation | JumpStarter ablations | 300 | 4.190 | [4.151, 4.230] | 11723.597 | 0.000 | 917.893 | +0.079 | [0.027, 0.132] | 154/35/111 |
| Random selection | JumpStarter ablations | 300 | 4.142 | [4.095, 4.189] | 24145.507 | 296.670 | 1091.680 | +0.128 | [0.069, 0.187] | 163/31/106 |
| No reuse | JumpStarter ablations | 300 | 4.088 | [4.040, 4.136] | 19779.850 | 238.807 | 954.773 | +0.182 | [0.125, 0.239] | 171/34/95 |
| No selection | JumpStarter ablations | 300 | 4.082 | [4.030, 4.133] | 26955.173 | 436.727 | 1117.337 | +0.188 | [0.128, 0.249] | 174/20/106 |

# Failure-Case Analysis

Paired over matched simulation profiles. Delta = first-named condition minus second; a profile is a tie when |delta| <= 1e-09 on the study-quality score. Loss rate = losses / n.

## 1. JumpStarter-Shallow vs. Single-turn decomposition

| n | Mean delta | 95% CI | W/T/L | Loss rate | Loss-or-tie rate |
| ---: | ---: | --- | ---: | ---: | ---: |
| 300 | +0.220 | [+0.164, +0.275] | 197/11/92 | 30.7% | 34.3% |

Median win +0.450, median loss -0.275; 50.0% of losses are within 0.25 and 81.5% within 0.50.

## 2. Where the gains thin out (JumpStarter-Shallow - Single-turn decomposition)

### By complexity

| Bucket | n | Mean delta | 95% CI | W/T/L | Loss rate |
| --- | ---: | ---: | --- | ---: | ---: |
| `complex` | 150 | +0.251 | [+0.166, +0.336] | 100/4/46 | 30.7% |
| `simple` | 150 | +0.188 | [+0.116, +0.260] | 97/7/46 | 30.7% |

### By time horizon

| Bucket | n | Mean delta | 95% CI | W/T/L | Loss rate |
| --- | ---: | ---: | --- | ---: | ---: |
| `months+` | 210 | +0.230 | [+0.164, +0.296] | 144/6/60 | 28.6% |
| `weeks` | 90 | +0.194 | [+0.090, +0.299] | 53/5/32 | 35.6% |

### By domain

| Bucket | n | Mean delta | 95% CI | W/T/L | Loss rate |
| --- | ---: | ---: | --- | ---: | ---: |
| `career_education` | 80 | +0.167 | [+0.055, +0.279] | 48/2/30 | 37.5% |
| `creative_personal` | 70 | +0.289 | [+0.177, +0.400] | 55/1/14 | 20.0% |
| `events_coordination` | 50 | +0.255 | [+0.140, +0.370] | 33/3/14 | 28.0% |
| `everyday_admin_home` | 70 | +0.166 | [+0.057, +0.274] | 43/4/23 | 32.9% |
| `health_wellness_training` | 30 | +0.265 | [+0.030, +0.500] | 18/1/11 | 36.7% |

### By complexity x domain

| Bucket | n | Mean delta | 95% CI | W/T/L | Loss rate |
| --- | ---: | ---: | --- | ---: | ---: |
| `complex x career_education` | 60 | +0.128 | [+0.003, +0.253] | 34/2/24 | 40.0% |
| `complex x creative_personal` | 35 | +0.347 | [+0.169, +0.525] | 29/0/6 | 17.1% |
| `complex x events_coordination` | 20 | +0.255 | [+0.054, +0.456] | 11/2/7 | 35.0% |
| `complex x everyday_admin_home` | 20 | +0.310 | [+0.122, +0.498] | 16/0/4 | 20.0% |
| `complex x health_wellness_training` | 15 | +0.433 | [+0.031, +0.836] | 10/0/5 | 33.3% |
| `simple x career_education` | 20 | +0.282 | [+0.042, +0.523] | 14/0/6 | 30.0% |
| `simple x creative_personal` | 35 | +0.230 | [+0.096, +0.364] | 26/1/8 | 22.9% |
| `simple x events_coordination` | 30 | +0.255 | [+0.115, +0.395] | 22/1/7 | 23.3% |
| `simple x everyday_admin_home` | 50 | +0.108 | [-0.022, +0.238] | 27/4/19 | 38.0% |
| `simple x health_wellness_training` | 15 | +0.097 | [-0.132, +0.325] | 8/1/6 | 40.0% |

### By persona

| Bucket | n | Mean delta | 95% CI | W/T/L | Loss rate |
| --- | ---: | ---: | --- | ---: | ---: |
| `P10_base` | 15 | +0.297 | [+0.058, +0.535] | 11/0/4 | 26.7% |
| `P10_variant_context_richness_medium` | 15 | +0.543 | [+0.350, +0.736] | 14/0/1 | 6.7% |
| `P2_base` | 15 | +0.160 | [-0.102, +0.422] | 11/0/4 | 26.7% |
| `P2_variant_context_richness_low` | 15 | +0.123 | [-0.154, +0.401] | 8/1/6 | 40.0% |
| `P2_variant_decision_style_collaborative` | 15 | +0.450 | [+0.072, +0.828] | 11/1/3 | 20.0% |
| `P3_base` | 15 | +0.357 | [+0.114, +0.600] | 10/0/5 | 33.3% |
| `P3_variant_context_richness_high` | 15 | +0.190 | [+0.016, +0.364] | 10/0/5 | 33.3% |
| `P4_base` | 15 | +0.147 | [-0.126, +0.420] | 9/1/5 | 33.3% |
| `P4_variant_decision_style_deferential` | 15 | +0.150 | [-0.035, +0.335] | 9/1/5 | 33.3% |
| `P5_base` | 15 | +0.253 | [+0.086, +0.421] | 13/0/2 | 13.3% |
| `P5_variant_decision_style_opinionated` | 15 | +0.103 | [-0.098, +0.304] | 7/1/7 | 46.7% |
| `P6_base` | 15 | +0.010 | [-0.191, +0.211] | 7/1/7 | 46.7% |
| `P6_variant_communication_style_balanced` | 15 | -0.000 | [-0.233, +0.233] | 7/1/7 | 46.7% |
| `P6_variant_communication_style_terse` | 15 | +0.280 | [+0.030, +0.530] | 11/0/4 | 26.7% |
| `P7_base` | 15 | +0.067 | [-0.124, +0.258] | 7/1/7 | 46.7% |
| `P7_variant_communication_style_verbose` | 15 | +0.097 | [-0.115, +0.308] | 9/1/5 | 33.3% |
| `P8_base` | 15 | +0.400 | [-0.013, +0.813] | 10/0/5 | 33.3% |
| `P8_variant_expertise_level_novice` | 15 | +0.227 | [+0.070, +0.383] | 13/0/2 | 13.3% |
| `P9_base` | 15 | +0.257 | [+0.057, +0.456] | 10/1/4 | 26.7% |
| `P9_variant_expertise_level_intermediate` | 15 | +0.280 | [-0.038, +0.598] | 10/1/4 | 26.7% |

### By persona context richness

| Bucket | n | Mean delta | 95% CI | W/T/L | Loss rate |
| --- | ---: | ---: | --- | ---: | ---: |
| `high` | 60 | +0.278 | [+0.147, +0.409] | 44/0/16 | 26.7% |
| `low` | 45 | +0.096 | [-0.034, +0.225] | 24/3/18 | 40.0% |
| `medium` | 195 | +0.230 | [+0.161, +0.299] | 129/8/58 | 29.7% |

## 3. Per-dimension delta (JumpStarter-Shallow - Single-turn decomposition)

| Dimension | All (n=300) | Loss profiles (n=92) | Win profiles (n=197) |
| --- | ---: | ---: | ---: |
| `context_curation_reuse` | +1.357 | +0.837 | +1.599 |
| `personalization_context_grounding` | +0.660 | +0.076 | +0.949 |
| `workflow_progress_support` | +0.190 | -0.402 | +0.482 |
| `no_contradiction_hallucination` | +0.277 | +0.000 | +0.401 |
| `specificity` | +0.060 | -0.413 | +0.299 |
| `completeness_coverage` | +0.257 | -0.304 | +0.513 |
| `decomposition_quality` | +0.120 | -0.315 | +0.335 |
| `plan_quality` | -0.113 | -0.728 | +0.178 |
| `user_burden_reduction` | -0.067 | -0.641 | +0.213 |
| `tangible_result_quality` | -0.017 | -0.609 | +0.289 |
| `confidence_support` | -0.107 | -0.598 | +0.142 |
| `overall` | -0.010 | -0.565 | +0.264 |

Mean output words, all profiles: JumpStarter-Shallow 1087 vs. Single-turn decomposition 357; loss profiles: 1082 vs. 385.

## 4. JumpStarter-Recursive vs. Single-turn decomposition

| Bucket | n | Mean delta | 95% CI | W/T/L | Loss rate |
| --- | ---: | ---: | --- | ---: | ---: |
| `all` | 300 | +0.146 | [+0.087, +0.205] | 186/9/105 | 35.0% |
| `complex` | 150 | +0.238 | [+0.148, +0.328] | 106/4/40 | 26.7% |
| `simple` | 150 | +0.054 | [-0.019, +0.128] | 80/5/65 | 43.3% |

## 5. Depth failure mode (JumpStarter-Recursive - JumpStarter-Shallow)

| Bucket | n | Mean delta | 95% CI | W/T/L | Loss rate |
| --- | ---: | ---: | --- | ---: | ---: |
| `all` | 300 | -0.073 | [-0.130, -0.017] | 130/12/158 | 52.7% |
| `complex` | 150 | -0.013 | [-0.096, +0.070] | 77/7/66 | 44.0% |
| `simple` | 150 | -0.134 | [-0.209, -0.058] | 53/5/92 | 61.3% |

| Dimension | Mean delta | 95% CI |
| --- | ---: | --- |
| `context_curation_reuse` | +0.183 | [+0.094, +0.273] |
| `personalization_context_grounding` | -0.103 | [-0.197, -0.010] |
| `workflow_progress_support` | +0.170 | [+0.086, +0.254] |
| `no_contradiction_hallucination` | -1.143 | [-1.284, -1.003] |
| `specificity` | +0.047 | [-0.027, +0.120] |
| `completeness_coverage` | -0.253 | [-0.340, -0.167] |
| `decomposition_quality` | -0.107 | [-0.180, -0.034] |
| `plan_quality` | -0.057 | [-0.129, +0.016] |
| `user_burden_reduction` | +0.017 | [-0.063, +0.096] |
| `tangible_result_quality` | -0.357 | [-0.449, -0.265] |
| `confidence_support` | -0.007 | [-0.080, +0.067] |
| `overall` | -0.117 | [-0.189, -0.045] |

## 6. Largest-margin losses (JumpStarter-Shallow - Single-turn decomposition)

| Delta | Goal | Complexity / domain | Persona | Worst dimensions |
| ---: | --- | --- | --- | --- |
| -1.150 | G015: Switch to a data analyst career | complex / career_education | `P4_base` | completeness_coverage -2, plan_quality -2, confidence_support -1 |
| -1.000 | G037: Declutter a crowded home office | simple / everyday_admin_home | `P2_base` | confidence_support -2, overall -2, tangible_result_quality -2 |
| -0.950 | G042: Adopt a first rescue cat | simple / everyday_admin_home | `P2_variant_context_richness_low` | overall -2, user_burden_reduction -2, completeness_coverage -1 |
| -0.950 | G020: Choose a graduate program | complex / career_education | `P9_variant_expertise_level_intermediate` | workflow_progress_support -2, completeness_coverage -1, confidence_support -1 |
| -0.800 | G028: Compose an original music EP | complex / creative_personal | `P7_variant_communication_style_verbose` | plan_quality -2, user_burden_reduction -2, confidence_support -1 |
| -0.750 | G010: Apply for NSF CSGrad4US Fellowship | complex / career_education | `P2_variant_decision_style_collaborative` | tangible_result_quality -2, confidence_support -1, decomposition_quality -1 |
| -0.750 | G036: Set up a household budget | simple / everyday_admin_home | `P6_base` | tangible_result_quality -2, completeness_coverage -1, confidence_support -1 |
| -0.750 | G047: Prepare for international travel paperwork | simple / everyday_admin_home | `P2_variant_context_richness_low` | user_burden_reduction -2, workflow_progress_support -2, confidence_support -1 |
| -0.700 | G056: Build a sustainable sleep routine | simple / health_wellness_training | `P2_base` | decomposition_quality -2, confidence_support -1, no_contradiction_hallucination -1 |
| -0.700 | G027: Plan a personal photo essay | simple / creative_personal | `P6_variant_communication_style_terse` | completeness_coverage -1, confidence_support -1, decomposition_quality -1 |

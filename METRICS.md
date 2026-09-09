# What this project measures, and what it measured

GENERATED -- do not edit. Every number here is rendered from the record that produced it (`results/*.json`), so it cannot drift from the run it describes. Remake it with:

```
python3 tools/sweep.py --apply      # measure
books bench report                  # render this file
```

All cells were computed at commit `42a6d749e8f87765e4ff3016662791e112cb7e4b`, between 2026-09-09T14:38:48+0300 and 2026-09-09T15:01:57+0300.

Each cell is the value with the count behind it. Where a metric was counted over only PART of a bench, the cell says so; where it says nothing, it was counted over all of it.

A scalar's name carries an arrow: **↑** better higher, **↓** better lower, **=** neither end is better. An `=` scalar either describes the bench or the run, so ranking models by it means nothing, or it is a GUARD -- read across models, but beside a ranked number rather than as one. `area_under_boxes` is a guard: a model that boxes the whole sheet takes 100 % of the ink with it, so a high share of ink is only worth what the area beside it says. Two cells that cannot be compared are never put in one column without saying so.

`—` is a value that does not exist, and the reason is under its table. `·` is a metric that does not apply to that pair. **`?` is NOT MEASURED** -- the run was never made, or was scored before this row existed, and either way it is not a result. A whole row of `?` means the sweep has not been run since that number was added; it does not mean the benches cannot answer it.

## What is not in this table

**The reading.** Level two runs a VLM on a rented card and costs money; nothing here rents anything. No reading run has been measured against a truth yet, so there is no reading row at all -- `docs/architecture.md` says in three reasons why, before any money is spent.

**Runs of another level.** This is a cross-DETECTOR table: every number is a property of the boxes a model drew. A level-two run carries the boxes of whatever detector made its pages, so its numbers describe that detector and not the reader named on the directory -- in the model column the reader would read as having earned them. 3 such runs are kept out of the tables above and given a section of their own at the end: `feynman-1` / `PaddleOCR-VL-1.6-0.9B` (read), `ogneupory-vl2` / `PaddleOCR-VL-1.6-0.9B+pages20` (read), `ogneupory-vl2` / `PaddleOCR-VL-1.6-0.9B` (read).

**Anything a bench cannot support.** A metric whose prerequisites a bench does not meet is absent, not zero, and the reason is printed under the table it would have been in -- taken from the record, not typed here. A sentence typed into this document about a particular bench was wrong for a day while the dash two lines below it was right; that is what a generated file is for.

Three questions, and every row below answers one of them. Each keeps its own instrument and its own denominator -- nothing here is averaged into a score, because the two metrics that would be averaged each record in their own header that one combined number trades one defect for another.

## How much of the book survived

Ink, objects and blocks -- four populations with four denominators, which is why they are four rows and not an average. Read them with the box-shape guards below: a model that boxes the whole sheet takes 100 % of the ink having found nothing.

### artefacts_found ↑ — tables and pictures found

| model | annopage | atlas | hard | hard36 | katalog | matematika | slovar | spravochnik | zhurnal |
|---|---|---|---|---|---|---|---|---|---|
| `PP-DocLayoutV2` | 0.567 <sub>698/1232</sub> | 0.750 <sub>12/16</sub> | 0.429 <sub>316/736</sub> | 0.199 <sub>80/403</sub> | 0.846 <sub>11/13</sub> | 0.704 <sub>19/27</sub> | 0.667 <sub>2/3</sub> | 0.756 <sub>34/45</sub> | 0.833 <sub>5/6</sub> |
| `PP-DocLayoutV3` | 0.553 <sub>681/1232</sub> | 0.688 <sub>11/16</sub> | 0.401 <sub>295/736</sub> | 0.206 <sub>83/403</sub> | 0.846 <sub>11/13</sub> | 0.741 <sub>20/27</sub> | 0.667 <sub>2/3</sub> | 0.689 <sub>31/45</sub> | 1.000 <sub>6/6</sub> |
| `PP-DocLayout_plus-L` | 0.511 <sub>630/1232</sub> | 0.875 <sub>14/16</sub> | 0.357 <sub>263/736</sub> | 0.176 <sub>71/403</sub> | 0.769 <sub>10/13</sub> | 0.778 <sub>21/27</sub> | 1.000 <sub>3/3</sub> | 0.733 <sub>33/45</sub> | 1.000 <sub>6/6</sub> |
| `docling-egret` | 0.537 <sub>661/1232</sub> | 0.750 <sub>12/16</sub> | 0.402 <sub>296/736</sub> | 0.191 <sub>77/403</sub> | 0.538 <sub>7/13</sub> | 0.111 <sub>3/27</sub> | 0.667 <sub>2/3</sub> | 0.733 <sub>33/45</sub> | 1.000 <sub>6/6</sub> |
| `docling-heron` | 0.563 <sub>694/1232</sub> | 0.875 <sub>14/16</sub> | 0.431 <sub>317/736</sub> | 0.218 <sub>88/403</sub> | 0.462 <sub>6/13</sub> | 0.111 <sub>3/27</sub> | 0.667 <sub>2/3</sub> | 0.800 <sub>36/45</sub> | 1.000 <sub>6/6</sub> |
| `yolox_l0.05` | 0.299 <sub>368/1232</sub> | 0.688 <sub>11/16</sub> | 0.166 <sub>122/736</sub> | 0.094 <sub>38/403</sub> | 0.308 <sub>4/13</sub> | 0.000 <sub>0/27</sub> | 0.333 <sub>1/3</sub> | 0.267 <sub>12/45</sub> | 0.667 <sub>4/6</sub> |

### text_furniture_found ↑ — text and furniture found

| model | annopage | atlas | hard | hard36 | katalog | matematika | slovar | spravochnik | zhurnal |
|---|---|---|---|---|---|---|---|---|---|
| `PP-DocLayoutV2` | — | 1.000 <sub>12/12</sub> | 0.918 <sub>45/49</sub> <sub>over 6/130 pages</sub> | — | 0.891 <sub>49/55</sub> | 1.000 <sub>104/104</sub> | 0.990 <sub>515/520</sub> | 0.955 <sub>322/337</sub> | 0.956 <sub>175/183</sub> |
| `PP-DocLayoutV3` | — | 1.000 <sub>12/12</sub> | 0.939 <sub>46/49</sub> <sub>over 6/130 pages</sub> | — | 0.909 <sub>50/55</sub> | 1.000 <sub>104/104</sub> | 0.948 <sub>493/520</sub> | 0.760 <sub>256/337</sub> | 0.874 <sub>160/183</sub> |
| `PP-DocLayout_plus-L` | — | 0.667 <sub>8/12</sub> | 0.918 <sub>45/49</sub> <sub>over 6/130 pages</sub> | — | 0.782 <sub>43/55</sub> | 1.000 <sub>104/104</sub> | 0.454 <sub>236/520</sub> | 0.976 <sub>329/337</sub> | 0.956 <sub>175/183</sub> |
| `docling-egret` | — | 0.917 <sub>11/12</sub> | 0.857 <sub>42/49</sub> <sub>over 6/130 pages</sub> | — | 0.891 <sub>49/55</sub> | 0.933 <sub>97/104</sub> | 0.950 <sub>494/520</sub> | 0.955 <sub>322/337</sub> | 0.984 <sub>180/183</sub> |
| `docling-heron` | — | 1.000 <sub>12/12</sub> | 0.939 <sub>46/49</sub> <sub>over 6/130 pages</sub> | — | 0.964 <sub>53/55</sub> | 0.990 <sub>103/104</sub> | 0.994 <sub>517/520</sub> | 0.991 <sub>334/337</sub> | 0.989 <sub>181/183</sub> |
| `yolox_l0.05` | — | 0.500 <sub>6/12</sub> | 0.796 <sub>39/49</sub> <sub>over 6/130 pages</sub> | — | 0.600 <sub>33/55</sub> | 0.933 <sub>97/104</sub> | 0.931 <sub>484/520</sub> | 0.932 <sub>314/337</sub> | 0.874 <sub>160/183</sub> |

- a dash means: text and furniture NOT MARKED in this truth

### ink_under_boxes ↑ — ink that lands inside some box

| model | annopage | atlas | hard | hard36 | katalog | matematika | slovar | spravochnik | zhurnal |
|---|---|---|---|---|---|---|---|---|---|
| `PP-DocLayoutV2` | 0.727 <sub>537247851/739099410</sub> | 0.860 <sub>969214/1127438</sub> | 0.771 <sub>74357353/96454397</sub> | 0.757 <sub>10495785/13857314</sub> | 0.967 <sub>1246014/1288204</sub> | 0.994 <sub>1819435/1830374</sub> | 0.976 <sub>1032695/1057663</sub> | 0.963 <sub>7170933/7443469</sub> | 0.990 <sub>2343459/2367945</sub> |
| `PP-DocLayoutV3` | 0.665 <sub>491613557/739099410</sub> | 0.874 <sub>985726/1127438</sub> | 0.698 <sub>67298678/96454397</sub> | 0.700 <sub>9700902/13857314</sub> | 0.924 <sub>1190444/1288204</sub> | 0.994 <sub>1820031/1830374</sub> | 0.986 <sub>1043227/1057663</sub> | 0.953 <sub>7090749/7443469</sub> | 0.900 <sub>2131854/2367945</sub> |
| `PP-DocLayout_plus-L` | 0.745 <sub>550633038/739099410</sub> | 0.898 <sub>1012742/1127438</sub> | 0.782 <sub>75471257/96454397</sub> | 0.734 <sub>10175878/13857314</sub> | 0.965 <sub>1243512/1288204</sub> | 0.993 <sub>1818237/1830374</sub> | 0.868 <sub>918559/1057663</sub> | 0.969 <sub>7211591/7443469</sub> | 0.988 <sub>2340141/2367945</sub> |
| `docling-egret` | 0.761 <sub>562593874/739099410</sub> | 0.989 <sub>1114659/1127438</sub> | 0.791 <sub>76324624/96454397</sub> | 0.752 <sub>10414007/13857314</sub> | 0.867 <sub>1117305/1288204</sub> | 0.992 <sub>1816455/1830374</sub> | 0.980 <sub>1036339/1057663</sub> | 0.967 <sub>7197149/7443469</sub> | 0.990 <sub>2345179/2367945</sub> |
| `docling-heron` | 0.754 <sub>557443399/739099410</sub> | 0.910 <sub>1026408/1127438</sub> | 0.795 <sub>76657835/96454397</sub> | 0.773 <sub>10718079/13857314</sub> | 0.904 <sub>1164323/1288204</sub> | 0.995 <sub>1820990/1830374</sub> | 0.982 <sub>1038992/1057663</sub> | 0.973 <sub>7244408/7443469</sub> | 0.990 <sub>2344706/2367945</sub> |
| `yolox_l0.05` | 0.534 <sub>394361133/739099410</sub> | 0.881 <sub>993304/1127438</sub> | 0.554 <sub>53401221/96454397</sub> | 0.610 <sub>8449863/13857314</sub> | 0.880 <sub>1133679/1288204</sub> | 0.956 <sub>1749063/1830374</sub> | 0.897 <sub>949009/1057663</sub> | 0.906 <sub>6743174/7443469</sub> | 0.890 <sub>2107054/2367945</sub> |

### ink_under_boxes_clean ↑ — the same over the ink that is ink: binding shadow and scan edge discarded from both sides

| model | annopage | atlas | hard | hard36 | katalog | matematika | slovar | spravochnik | zhurnal |
|---|---|---|---|---|---|---|---|---|---|
| `PP-DocLayoutV2` | 0.751 <sub>535089502/712341651</sub> | 0.860 <sub>969214/1127438</sub> | 0.790 <sub>74338517/94131254</sub> | 0.779 <sub>10475009/13450086</sub> | 0.974 <sub>1197423/1229718</sub> | 0.994 <sub>1819435/1830374</sub> | 0.976 <sub>1032695/1057663</sub> | 0.979 <sub>7170933/7327794</sub> | 0.990 <sub>2343459/2367945</sub> |
| `PP-DocLayoutV3` | 0.687 <sub>489721197/712341651</sub> | 0.874 <sub>985726/1127438</sub> | 0.715 <sub>67277234/94131254</sub> | 0.721 <sub>9693175/13450086</sub> | 0.928 <sub>1141634/1229718</sub> | 0.994 <sub>1820031/1830374</sub> | 0.986 <sub>1043227/1057663</sub> | 0.958 <sub>7017726/7327794</sub> | 0.900 <sub>2131854/2367945</sub> |
| `PP-DocLayout_plus-L` | 0.769 <sub>548069179/712341651</sub> | 0.898 <sub>1012742/1127438</sub> | 0.801 <sub>75445199/94131254</sub> | 0.756 <sub>10169710/13450086</sub> | 0.972 <sub>1195382/1229718</sub> | 0.993 <sub>1818237/1830374</sub> | 0.868 <sub>918559/1057663</sub> | 0.984 <sub>7211591/7327794</sub> | 0.988 <sub>2340141/2367945</sub> |
| `docling-egret` | 0.786 <sub>560132483/712341651</sub> | 0.989 <sub>1114659/1127438</sub> | 0.810 <sub>76279004/94131254</sub> | 0.774 <sub>10405280/13450086</sub> | 0.909 <sub>1117305/1229718</sub> | 0.992 <sub>1816455/1830374</sub> | 0.980 <sub>1036339/1057663</sub> | 0.982 <sub>7197149/7327794</sub> | 0.990 <sub>2345179/2367945</sub> |
| `docling-heron` | 0.780 <sub>555463036/712341651</sub> | 0.910 <sub>1026408/1127438</sub> | 0.814 <sub>76616803/94131254</sub> | 0.795 <sub>10694336/13450086</sub> | 0.907 <sub>1115883/1229718</sub> | 0.995 <sub>1820990/1830374</sub> | 0.982 <sub>1038992/1057663</sub> | 0.986 <sub>7227284/7327794</sub> | 0.990 <sub>2344706/2367945</sub> |
| `yolox_l0.05` | 0.552 <sub>393074841/712341651</sub> | 0.881 <sub>993304/1127438</sub> | 0.567 <sub>53384887/94131254</sub> | 0.628 <sub>8441329/13450086</sub> | 0.882 <sub>1084222/1229718</sub> | 0.956 <sub>1749063/1830374</sub> | 0.897 <sub>949009/1057663</sub> | 0.920 <sub>6743174/7327794</sub> | 0.890 <sub>2107054/2367945</sub> |

### ink_as_text ↑ — ink that leaves the book as text rather than as a picture of itself

| model | annopage | atlas | hard | hard36 | katalog | matematika | slovar | spravochnik | zhurnal |
|---|---|---|---|---|---|---|---|---|---|
| `PP-DocLayoutV2` | — | — | — | — | — | — | — | — | — |
| `PP-DocLayoutV3` | — | — | — | — | — | — | — | — | — |
| `PP-DocLayout_plus-L` | — | — | — | — | — | — | — | — | — |
| `docling-egret` | — | — | — | — | — | — | — | — | — |
| `docling-heron` | — | — | — | — | — | — | — | — | — |
| `yolox_l0.05` | — | — | — | — | — | — | — | — | — |

- a dash means: this run read nothing: every block would leave as a picture, which is not a measurement of one

### object_ink_preserved ↑ — ink of the truth objects that survives inside boxes

| model | annopage | atlas | hard | hard36 | katalog | matematika | slovar | spravochnik | zhurnal |
|---|---|---|---|---|---|---|---|---|---|
| `PP-DocLayoutV2` | 0.894 <sub>149614306/167384248</sub> | 0.903 <sub>893972/989602</sub> | 0.922 <sub>26637623/28887708</sub> | 0.948 <sub>5527339/5828260</sub> | 1.000 <sub>782395/782450</sub> | 0.746 <sub>24672/33072</sub> | 0.928 <sub>33218/35792</sub> | 0.925 <sub>1159274/1253127</sub> | 0.913 <sub>149586/163915</sub> |
| `PP-DocLayoutV3` | 0.915 <sub>153165766/167384248</sub> | 0.932 <sub>922349/989602</sub> | 0.883 <sub>25503180/28887708</sub> | 0.899 <sub>5240006/5828260</sub> | 0.925 <sub>723781/782450</sub> | 0.948 <sub>31360/33072</sub> | 0.933 <sub>33409/35792</sub> | 0.945 <sub>1184191/1253127</sub> | 0.987 <sub>161766/163915</sub> |
| `PP-DocLayout_plus-L` | 0.945 <sub>158095780/167384248</sub> | 0.948 <sub>937895/989602</sub> | 0.936 <sub>27048832/28887708</sub> | 0.948 <sub>5527880/5828260</sub> | 0.746 <sub>583683/782450</sub> | 0.887 <sub>29335/33072</sub> | 0.979 <sub>35041/35792</sub> | 0.945 <sub>1184531/1253127</sub> | 0.983 <sub>161057/163915</sub> |
| `docling-egret` | 0.893 <sub>149507725/167384248</sub> | 1.000 <sub>989344/989602</sub> | 0.933 <sub>26966397/28887708</sub> | 0.916 <sub>5338682/5828260</sub> | 0.380 <sub>297618/782450</sub> | 0.855 <sub>28267/33072</sub> | 0.150 <sub>5381/35792</sub> | 0.728 <sub>912197/1253127</sub> | 0.999 <sub>163764/163915</sub> |
| `docling-heron` | 0.945 <sub>158239797/167384248</sub> | 0.954 <sub>944195/989602</sub> | 0.900 <sub>26005793/28887708</sub> | 0.949 <sub>5532404/5828260</sub> | 0.556 <sub>434907/782450</sub> | 0.867 <sub>28664/33072</sub> | 0.159 <sub>5681/35792</sub> | 0.843 <sub>1056143/1253127</sub> | 0.997 <sub>163364/163915</sub> |
| `yolox_l0.05` | 0.719 <sub>120330962/167384248</sub> | 0.942 <sub>932686/989602</sub> | 0.697 <sub>20144631/28887708</sub> | 0.821 <sub>4785188/5828260</sub> | 0.748 <sub>585542/782450</sub> | 0.000 <sub>0/33072</sub> | 0.102 <sub>3662/35792</sub> | 0.707 <sub>886497/1253127</sub> | 0.898 <sub>147146/163915</sub> |

## Is the order right

Where the truth marks reading order, agreement with it; where it does not -- and it is marked on no real page in this project -- how often the assembled order jumps between columns.

### assembly_order ↑ — reading order of the assembled book agrees with truth

| model | annopage | atlas | hard | hard36 | katalog | matematika | slovar | spravochnik | zhurnal |
|---|---|---|---|---|---|---|---|---|---|
| `PP-DocLayoutV2` | — | 0.952 | 0.957 <sub>over 6/130 pages</sub> | — | 0.989 | 1.000 | 0.886 | 0.989 | 1.000 |
| `PP-DocLayoutV3` | — | 1.000 | 0.958 <sub>over 6/130 pages</sub> | — | 0.939 | 1.000 | 0.999 | 0.985 | 0.970 |
| `PP-DocLayout_plus-L` | — | 0.882 | 0.913 <sub>over 6/130 pages</sub> | — | 0.953 | 1.000 | 0.730 | 0.807 | 0.773 |
| `docling-egret` | — | 0.895 | 0.908 <sub>over 6/130 pages</sub> | — | 0.944 | 1.000 | 0.683 | 0.803 | 0.769 |
| `docling-heron` | — | 0.913 | 0.917 <sub>over 6/130 pages</sub> | — | 0.961 | 1.000 | 0.689 | 0.809 | 0.771 |
| `yolox_l0.05` | — | 0.900 | 0.904 <sub>over 6/130 pages</sub> | — | 0.936 | 1.000 | 0.686 | 0.798 | 0.749 |

- a dash means: truth carries no order: not marked on 600 of 600 pages
- a dash means: truth carries no order: not_said on 36 of 36 pages

### excess_jumps_per_transition ↓ — excess column jumps per move between boxes

| model | annopage | atlas | hard | hard36 | katalog | matematika | slovar | spravochnik | zhurnal |
|---|---|---|---|---|---|---|---|---|---|
| `PP-DocLayoutV2` | 0.539 <sub>501/930</sub> | 0.000 <sub>0/2</sub> | 0.583 <sub>193/331</sub> | 0.685 <sub>87/127</sub> | — | 0.909 <sub>10/11</sub> | 0.867 <sub>130/150</sub> | 0.091 <sub>2/22</sub> | 0.000 <sub>0/10</sub> |
| `PP-DocLayoutV3` | 0.533 <sub>498/934</sub> | 0.000 <sub>0/5</sub> | 0.610 <sub>214/351</sub> | 0.680 <sub>83/122</sub> | 0.967 <sub>347/359</sub> | 0.909 <sub>10/11</sub> | 0.548 <sub>23/42</sub> | 0.640 <sub>16/25</sub> | 0.714 <sub>20/28</sub> |
| `PP-DocLayout_plus-L` | 0.837 <sub>2164/2586</sub> | 0.400 <sub>2/5</sub> | 0.802 <sub>526/656</sub> | 0.787 <sub>159/202</sub> | 0.000 <sub>0/13</sub> | 0.909 <sub>10/11</sub> | 0.955 <sub>214/224</sub> | 0.897 <sub>131/146</sub> | 0.925 <sub>124/134</sub> |
| `docling-egret` | 0.868 <sub>2587/2981</sub> | 0.667 <sub>2/3</sub> | 0.820 <sub>547/667</sub> | 0.801 <sub>149/186</sub> | 0.077 <sub>2/26</sub> | — | 0.967 <sub>640/662</sub> | 0.891 <sub>204/229</sub> | 0.928 <sub>129/139</sub> |
| `docling-heron` | 0.872 <sub>2741/3144</sub> | 0.333 <sub>2/6</sub> | 0.825 <sub>577/699</sub> | 0.799 <sub>139/174</sub> | 0.250 <sub>5/20</sub> | 0.909 <sub>10/11</sub> | 0.956 <sub>475/497</sub> | 0.841 <sub>132/157</sub> | 0.933 <sub>140/150</sub> |
| `yolox_l0.05` | 0.792 <sub>1139/1438</sub> | 0.000 <sub>0/1</sub> | 0.747 <sub>221/296</sub> | 0.789 <sub>90/114</sub> | — | — | 0.958 <sub>431/450</sub> | 0.920 <sub>126/137</sub> | 0.931 <sub>122/131</sub> |

- a dash means: no page gathered two counted boxes: nothing to jump between

- counted over `model_rank`: `PP-DocLayoutV2`, `PP-DocLayoutV3`
- counted over `ours_top_down_left_right`: `docling-egret`, `docling-heron`, `yolox_l0.05`
- counted over `ours_top_down_left_right: the model gives no rank`: `PP-DocLayout_plus-L`
- **these are two different quantities**, and the columns are not comparable across the two groups.

### excess_jumps_per_transition_one_rule ↓ — the same with one ordering rule forced on every model, so the column compares boxes alone

| model | annopage | atlas | hard | hard36 | katalog | matematika | slovar | spravochnik | zhurnal |
|---|---|---|---|---|---|---|---|---|---|
| `PP-DocLayoutV2` | 0.852 <sub>2471/2900</sub> | 0.333 <sub>1/3</sub> | 0.829 <sub>669/807</sub> | 0.813 <sub>174/214</sub> | — | 0.909 <sub>10/11</sub> | 0.960 <sub>479/499</sub> | 0.868 <sub>131/151</sub> | 0.925 <sub>123/133</sub> |
| `PP-DocLayoutV3` | 0.837 <sub>2233/2669</sub> | 0.000 <sub>0/5</sub> | 0.801 <sub>551/688</sub> | 0.791 <sub>148/187</sub> | 0.967 <sub>348/360</sub> | 0.909 <sub>10/11</sub> | 0.961 <sub>466/485</sub> | 0.893 <sub>75/84</sub> | 0.930 <sub>106/114</sub> |
| `PP-DocLayout_plus-L` | 0.837 <sub>2164/2586</sub> | 0.400 <sub>2/5</sub> | 0.802 <sub>526/656</sub> | 0.787 <sub>159/202</sub> | 0.000 <sub>0/13</sub> | 0.909 <sub>10/11</sub> | 0.955 <sub>214/224</sub> | 0.897 <sub>131/146</sub> | 0.925 <sub>124/134</sub> |
| `docling-egret` | 0.868 <sub>2587/2981</sub> | 0.667 <sub>2/3</sub> | 0.820 <sub>547/667</sub> | 0.801 <sub>149/186</sub> | 0.077 <sub>2/26</sub> | — | 0.967 <sub>640/662</sub> | 0.891 <sub>204/229</sub> | 0.928 <sub>129/139</sub> |
| `docling-heron` | 0.872 <sub>2741/3144</sub> | 0.333 <sub>2/6</sub> | 0.825 <sub>577/699</sub> | 0.799 <sub>139/174</sub> | 0.250 <sub>5/20</sub> | 0.909 <sub>10/11</sub> | 0.956 <sub>475/497</sub> | 0.841 <sub>132/157</sub> | 0.933 <sub>140/150</sub> |
| `yolox_l0.05` | 0.792 <sub>1139/1438</sub> | 0.000 <sub>0/1</sub> | 0.747 <sub>221/296</sub> | 0.789 <sub>90/114</sub> | — | — | 0.958 <sub>431/450</sub> | 0.920 <sub>126/137</sub> | 0.931 <sub>122/131</sub> |

- a dash means: no page gathered two counted boxes: nothing to jump between

- counted over `model_rank`: `PP-DocLayoutV2`, `PP-DocLayoutV3`
- counted over `ours_top_down_left_right`: `docling-egret`, `docling-heron`, `yolox_l0.05`
- counted over `ours_top_down_left_right: the model gives no rank`: `PP-DocLayout_plus-L`
- **these are two different quantities**, and the columns are not comparable across the two groups.

## What failed, and how

The derivatives: an artefact can be missed, cut, called text, or merged with its neighbour, and those four account for every one that did not arrive whole.

### artefacts_not_seen ↓ — artefacts the model never boxed

| model | annopage | atlas | hard | hard36 | katalog | matematika | slovar | spravochnik | zhurnal |
|---|---|---|---|---|---|---|---|---|---|
| `PP-DocLayoutV2` | 0.067 <sub>82/1232</sub> | 0.188 <sub>3/16</sub> | 0.041 <sub>30/736</sub> | 0.032 <sub>13/403</sub> | 0.000 <sub>0/13</sub> | 0.148 <sub>4/27</sub> | 0.333 <sub>1/3</sub> | 0.044 <sub>2/45</sub> | 0.167 <sub>1/6</sub> |
| `PP-DocLayoutV3` | 0.121 <sub>149/1232</sub> | 0.125 <sub>2/16</sub> | 0.120 <sub>88/736</sub> | 0.139 <sub>56/403</sub> | 0.154 <sub>2/13</sub> | 0.185 <sub>5/27</sub> | 0.333 <sub>1/3</sub> | 0.067 <sub>3/45</sub> | 0.000 <sub>0/6</sub> |
| `PP-DocLayout_plus-L` | 0.060 <sub>74/1232</sub> | 0.125 <sub>2/16</sub> | 0.045 <sub>33/736</sub> | 0.037 <sub>15/403</sub> | 0.077 <sub>1/13</sub> | 0.000 <sub>0/27</sub> | 0.000 <sub>0/3</sub> | 0.044 <sub>2/45</sub> | 0.000 <sub>0/6</sub> |
| `docling-egret` | 0.057 <sub>70/1232</sub> | 0.000 <sub>0/16</sub> | 0.038 <sub>28/736</sub> | 0.092 <sub>37/403</sub> | 0.385 <sub>5/13</sub> | 0.148 <sub>4/27</sub> | 0.333 <sub>1/3</sub> | 0.067 <sub>3/45</sub> | 0.000 <sub>0/6</sub> |
| `docling-heron` | 0.056 <sub>69/1232</sub> | 0.062 <sub>1/16</sub> | 0.048 <sub>35/736</sub> | 0.055 <sub>22/403</sub> | 0.538 <sub>7/13</sub> | 0.074 <sub>2/27</sub> | 0.333 <sub>1/3</sub> | 0.022 <sub>1/45</sub> | 0.000 <sub>0/6</sub> |
| `yolox_l0.05` | 0.314 <sub>387/1232</sub> | 0.188 <sub>3/16</sub> | 0.288 <sub>212/736</sub> | 0.226 <sub>91/403</sub> | 0.154 <sub>2/13</sub> | 1.000 <sub>27/27</sub> | 0.667 <sub>2/3</sub> | 0.289 <sub>13/45</sub> | 0.167 <sub>1/6</sub> |

### artefacts_cropped ↓ — artefacts boxed, but cut short

| model | annopage | atlas | hard | hard36 | katalog | matematika | slovar | spravochnik | zhurnal |
|---|---|---|---|---|---|---|---|---|---|
| `PP-DocLayoutV2` | 0.069 <sub>85/1232</sub> | 0.000 <sub>0/16</sub> | 0.061 <sub>45/736</sub> | 0.052 <sub>21/403</sub> | 0.000 <sub>0/13</sub> | 0.037 <sub>1/27</sub> | 0.000 <sub>0/3</sub> | 0.022 <sub>1/45</sub> | 0.000 <sub>0/6</sub> |
| `PP-DocLayoutV3` | 0.075 <sub>92/1232</sub> | 0.062 <sub>1/16</sub> | 0.053 <sub>39/736</sub> | 0.045 <sub>18/403</sub> | 0.000 <sub>0/13</sub> | 0.000 <sub>0/27</sub> | 0.000 <sub>0/3</sub> | 0.000 <sub>0/45</sub> | 0.000 <sub>0/6</sub> |
| `PP-DocLayout_plus-L` | 0.132 <sub>163/1232</sub> | 0.062 <sub>1/16</sub> | 0.114 <sub>84/736</sub> | 0.107 <sub>43/403</sub> | 0.000 <sub>0/13</sub> | 0.481 <sub>13/27</sub> | 0.000 <sub>0/3</sub> | 0.022 <sub>1/45</sub> | 0.000 <sub>0/6</sub> |
| `docling-egret` | 0.108 <sub>133/1232</sub> | 0.000 <sub>0/16</sub> | 0.083 <sub>61/736</sub> | 0.050 <sub>20/403</sub> | 0.000 <sub>0/13</sub> | 0.074 <sub>2/27</sub> | 0.000 <sub>0/3</sub> | 0.022 <sub>1/45</sub> | 0.000 <sub>0/6</sub> |
| `docling-heron` | 0.113 <sub>139/1232</sub> | 0.000 <sub>0/16</sub> | 0.084 <sub>62/736</sub> | 0.060 <sub>24/403</sub> | 0.000 <sub>0/13</sub> | 0.000 <sub>0/27</sub> | 0.000 <sub>0/3</sub> | 0.022 <sub>1/45</sub> | 0.000 <sub>0/6</sub> |
| `yolox_l0.05` | 0.113 <sub>139/1232</sub> | 0.000 <sub>0/16</sub> | 0.076 <sub>56/736</sub> | 0.050 <sub>20/403</sub> | 0.385 <sub>5/13</sub> | 0.000 <sub>0/27</sub> | 0.000 <sub>0/3</sub> | 0.044 <sub>2/45</sub> | 0.000 <sub>0/6</sub> |

### artefacts_called_text ↓ — artefacts boxed as text: they leave as a line and the structure leaves with them

| model | annopage | atlas | hard | hard36 | katalog | matematika | slovar | spravochnik | zhurnal |
|---|---|---|---|---|---|---|---|---|---|
| `PP-DocLayoutV2` | 0.036 <sub>44/1232</sub> | 0.062 <sub>1/16</sub> | 0.029 <sub>21/736</sub> | 0.030 <sub>12/403</sub> | 0.000 <sub>0/13</sub> | 0.074 <sub>2/27</sub> | 0.000 <sub>0/3</sub> | 0.000 <sub>0/45</sub> | 0.000 <sub>0/6</sub> |
| `PP-DocLayoutV3` | 0.018 <sub>22/1232</sub> | 0.000 <sub>0/16</sub> | 0.012 <sub>9/736</sub> | 0.002 <sub>1/403</sub> | 0.000 <sub>0/13</sub> | 0.000 <sub>0/27</sub> | 0.000 <sub>0/3</sub> | 0.000 <sub>0/45</sub> | 0.000 <sub>0/6</sub> |
| `PP-DocLayout_plus-L` | 0.030 <sub>37/1232</sub> | 0.000 <sub>0/16</sub> | 0.031 <sub>23/736</sub> | 0.032 <sub>13/403</sub> | 0.000 <sub>0/13</sub> | 0.037 <sub>1/27</sub> | 0.000 <sub>0/3</sub> | 0.000 <sub>0/45</sub> | 0.000 <sub>0/6</sub> |
| `docling-egret` | 0.042 <sub>52/1232</sub> | 0.000 <sub>0/16</sub> | 0.035 <sub>26/736</sub> | 0.042 <sub>17/403</sub> | 0.077 <sub>1/13</sub> | 0.000 <sub>0/27</sub> | 0.000 <sub>0/3</sub> | 0.044 <sub>2/45</sub> | 0.000 <sub>0/6</sub> |
| `docling-heron` | 0.045 <sub>56/1232</sub> | 0.000 <sub>0/16</sub> | 0.042 <sub>31/736</sub> | 0.035 <sub>14/403</sub> | 0.000 <sub>0/13</sub> | 0.148 <sub>4/27</sub> | 0.000 <sub>0/3</sub> | 0.044 <sub>2/45</sub> | 0.000 <sub>0/6</sub> |
| `yolox_l0.05` | 0.014 <sub>17/1232</sub> | 0.000 <sub>0/16</sub> | 0.012 <sub>9/736</sub> | 0.010 <sub>4/403</sub> | 0.000 <sub>0/13</sub> | 0.000 <sub>0/27</sub> | 0.000 <sub>0/3</sub> | 0.000 <sub>0/45</sub> | 0.000 <sub>0/6</sub> |

### artefacts_merged = — artefacts sharing a box with a neighbour; no direction, since a wider picture is split at level two

| model | annopage | atlas | hard | hard36 | katalog | matematika | slovar | spravochnik | zhurnal |
|---|---|---|---|---|---|---|---|---|---|
| `PP-DocLayoutV2` | 0.304 <sub>375/1232</sub> | 0.000 <sub>0/16</sub> | 0.497 <sub>366/736</sub> | 0.737 <sub>297/403</sub> | 0.154 <sub>2/13</sub> | 0.074 <sub>2/27</sub> | 0.000 <sub>0/3</sub> | 0.156 <sub>7/45</sub> | 0.000 <sub>0/6</sub> |
| `PP-DocLayoutV3` | 0.293 <sub>361/1232</sub> | 0.125 <sub>2/16</sub> | 0.476 <sub>350/736</sub> | 0.667 <sub>269/403</sub> | 0.000 <sub>0/13</sub> | 0.074 <sub>2/27</sub> | 0.000 <sub>0/3</sub> | 0.244 <sub>11/45</sub> | 0.000 <sub>0/6</sub> |
| `PP-DocLayout_plus-L` | 0.344 <sub>424/1232</sub> | 0.000 <sub>0/16</sub> | 0.541 <sub>398/736</sub> | 0.720 <sub>290/403</sub> | 0.154 <sub>2/13</sub> | 0.370 <sub>10/27</sub> | 0.000 <sub>0/3</sub> | 0.178 <sub>8/45</sub> | 0.000 <sub>0/6</sub> |
| `docling-egret` | 0.320 <sub>394/1232</sub> | 0.250 <sub>4/16</sub> | 0.507 <sub>373/736</sub> | 0.670 <sub>270/403</sub> | 0.000 <sub>0/13</sub> | 0.481 <sub>13/27</sub> | 0.000 <sub>0/3</sub> | 0.156 <sub>7/45</sub> | 0.000 <sub>0/6</sub> |
| `docling-heron` | 0.297 <sub>366/1232</sub> | 0.062 <sub>1/16</sub> | 0.471 <sub>347/736</sub> | 0.705 <sub>284/403</sub> | 0.000 <sub>0/13</sub> | 0.667 <sub>18/27</sub> | 0.000 <sub>0/3</sub> | 0.133 <sub>6/45</sub> | 0.000 <sub>0/6</sub> |
| `yolox_l0.05` | 0.322 <sub>397/1232</sub> | 0.125 <sub>2/16</sub> | 0.515 <sub>379/736</sub> | 0.653 <sub>263/403</sub> | 0.000 <sub>0/13</sub> | 0.000 <sub>0/27</sub> | 0.000 <sub>0/3</sub> | 0.244 <sub>11/45</sub> | 0.000 <sub>0/6</sub> |

### charts_as_data ↓ — charts returned as a table of numbers: values read off a curve and placed in the book as text

| model | annopage | atlas | hard | hard36 | katalog | matematika | slovar | spravochnik | zhurnal |
|---|---|---|---|---|---|---|---|---|---|
| `PP-DocLayoutV2` | · | · | · | · | · | · | · | · | · |
| `PP-DocLayoutV3` | · | · | · | · | · | · | · | · | · |
| `PP-DocLayout_plus-L` | · | · | · | · | · | · | · | · | · |
| `docling-egret` | · | · | · | · | · | · | · | · | · |
| `docling-heron` | · | · | · | · | · | · | · | · | · |
| `yolox_l0.05` | · | · | · | · | · | · | · | · | · |

### looping ↓ — answers that repeat themselves

| model | annopage | atlas | hard | hard36 | katalog | matematika | slovar | spravochnik | zhurnal |
|---|---|---|---|---|---|---|---|---|---|
| `PP-DocLayoutV2` | · | · | · | · | · | · | · | · | · |
| `PP-DocLayoutV3` | · | · | · | · | · | · | · | · | · |
| `PP-DocLayout_plus-L` | · | · | · | · | · | · | · | · | · |
| `docling-egret` | · | · | · | · | · | · | · | · | · |
| `docling-heron` | · | · | · | · | · | · | · | · | · |
| `yolox_l0.05` | · | · | · | · | · | · | · | · | · |

## What the reading runs measured

A level-two run carries the boxes of whatever DETECTOR made its pages, so none of these numbers ranks the reader against the models above and none is in their tables. What it does carry is the only measurement of a book that has actually been read: how much of its ink leaves as text rather than as a picture of itself, and how much of the sheet was never information at all.

### feynman-1 — PaddleOCR-VL-1.6-0.9B (read)

| scalar | metric | value |
|---|---|---|
| `excess_jumps` ↓ | assembly | 0 |
| `excess_jumps_per_page` ↓ | assembly | 0.000 <sub>over 2/10 pages</sub> |
| `excess_jumps_per_transition` ↓ | assembly | 0.000 <sub>0/1</sub> |
| `excess_jumps_per_transition_one_rule` ↓ | assembly | 0.000 <sub>0/1</sub> |
| `pages_with_columns` = | assembly | 1 <sub>1/10</sub> |
| `transitions` = | assembly | 1 |
| `area_under_boxes` = | fitness | 0.858 <sub>6124063/7138535</sub> |
| `boxes_per_page` = | fitness | 5.800 <sub>58/10</sub> |
| `ink_as_picture` = | fitness | 0.011 <sub>11758/1084980</sub> |
| `ink_as_text` ↑ | fitness | 0.989 <sub>1073155/1084980</sub> |
| `ink_junk` = | fitness | 0.000 <sub>0/1084980</sub> |
| `ink_under_artefacts` = | fitness | 0.011 <sub>11758/1084980</sub> |
| `ink_under_boxes` ↑ | fitness | 1.000 <sub>1084913/1084980</sub> |
| `ink_under_boxes_clean` ↑ | fitness | 1.000 <sub>1084913/1084980</sub> |
| `median_box_area` = | fitness | 0.087 |
| `object_ink_preserved` ↑ | fitness | — |
| `objects_in_one_box` ↑ | fitness | — |
| `objects_intact` ↑ | fitness | — |
| `objects_left_as_text` ↓ | fitness | — |
| `objects_torn` ↓ | fitness | — |
| `objects_with_company` ↓ | fitness | — |
| `empty` ↓ | snapshot | 6 <sub>6/52</sub> |
| `fingerprint_verified` = | snapshot | 0 |
| `missing` ↓ | snapshot | 3 <sub>3/52</sub> |
| `values_present` = | snapshot | 49 <sub>49/52</sub> |

- a dash: no truth given: the object half needs it

### ogneupory-vl2 — PaddleOCR-VL-1.6-0.9B+pages20 (read)

| scalar | metric | value |
|---|---|---|
| `excess_jumps` ↓ | assembly | 10 |
| `excess_jumps_per_page` ↓ | assembly | 0.833 <sub>over 12/20 pages</sub> |
| `excess_jumps_per_transition` ↓ | assembly | 0.455 <sub>10/22</sub> |
| `excess_jumps_per_transition_one_rule` ↓ | assembly | 0.538 <sub>14/26</sub> |
| `pages_with_columns` = | assembly | 9 <sub>9/20</sub> |
| `transitions` = | assembly | 22 |
| `area_under_boxes` = | fitness | 0.659 <sub>10255807/15567096</sub> |
| `boxes_per_page` = | fitness | 13.150 <sub>263/20</sub> |
| `ink_as_picture` = | fitness | 0.065 <sub>124325/1916661</sub> |
| `ink_as_text` ↑ | fitness | 0.771 <sub>1477985/1916661</sub> |
| `ink_junk` = | fitness | 0.137 <sub>262866/1916661</sub> |
| `ink_under_artefacts` = | fitness | 0.065 <sub>124325/1916661</sub> |
| `ink_under_boxes` ↑ | fitness | 0.836 <sub>1602310/1916661</sub> |
| `ink_under_boxes_clean` ↑ | fitness | 0.960 <sub>1587735/1653795</sub> |
| `median_box_area` = | fitness | 0.036 |
| `object_ink_preserved` ↑ | fitness | — |
| `objects_in_one_box` ↑ | fitness | — |
| `objects_intact` ↑ | fitness | — |
| `objects_left_as_text` ↓ | fitness | — |
| `objects_torn` ↓ | fitness | — |
| `objects_with_company` ↓ | fitness | — |
| `empty` ↓ | snapshot | 4 <sub>4/52</sub> |
| `fingerprint_verified` = | snapshot | 0 |
| `missing` ↓ | snapshot | 3 <sub>3/52</sub> |
| `values_present` = | snapshot | 49 <sub>49/52</sub> |

- a dash: no truth given: the object half needs it

### ogneupory-vl2 — PaddleOCR-VL-1.6-0.9B (read)

| scalar | metric | value |
|---|---|---|
| `excess_jumps` ↓ | assembly | 763 |
| `excess_jumps_per_page` ↓ | assembly | 2.668 <sub>over 286/378 pages</sub> |
| `excess_jumps_per_transition` ↓ | assembly | 0.672 <sub>763/1136</sub> |
| `excess_jumps_per_transition_one_rule` ↓ | assembly | 0.690 <sub>832/1205</sub> |
| `pages_with_columns` = | assembly | 224 <sub>224/378</sub> |
| `transitions` = | assembly | 1136 |
| `area_under_boxes` = | fitness | 0.638 <sub>187899322/294316190</sub> |
| `boxes_per_page` = | fitness | 16.286 <sub>6156/378</sub> |
| `ink_as_picture` = | fitness | 0.087 <sub>2979534/34181441</sub> |
| `ink_as_text` ↑ | fitness | 0.769 <sub>26300614/34181441</sub> |
| `ink_junk` = | fitness | 0.104 <sub>3569827/34181441</sub> |
| `ink_under_artefacts` = | fitness | 0.087 <sub>2957800/34181441</sub> |
| `ink_under_boxes` ↑ | fitness | 0.857 <sub>29280148/34181441</sub> |
| `ink_under_boxes_clean` ↑ | fitness | 0.954 <sub>29188719/30611614</sub> |
| `median_box_area` = | fitness | 0.011 |
| `object_ink_preserved` ↑ | fitness | — |
| `objects_in_one_box` ↑ | fitness | — |
| `objects_intact` ↑ | fitness | — |
| `objects_left_as_text` ↓ | fitness | — |
| `objects_torn` ↓ | fitness | — |
| `objects_with_company` ↓ | fitness | — |
| `empty` ↓ | snapshot | 4 <sub>4/52</sub> |
| `fingerprint_verified` = | snapshot | 0 |
| `missing` ↓ | snapshot | 3 <sub>3/52</sub> |
| `values_present` = | snapshot | 49 <sub>49/52</sub> |

- a dash: no truth given: the object half needs it

## Every scalar, bench by bench

### annopage

**assembly**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `excess_jumps` ↓ | 501 | 498 | 2164 | 2587 | 2741 | 1139 |
| `excess_jumps_per_page` ↓ | 1.080 <sub>over 464/600 pages</sub> | 1.107 <sub>over 450/600 pages</sub> | 4.941 <sub>over 438/600 pages</sub> | 5.093 <sub>over 508/600 pages</sub> | 5.281 <sub>over 519/600 pages</sub> | 3.360 <sub>over 339/600 pages</sub> |
| `excess_jumps_per_transition` ↓ | 0.539 <sub>501/930</sub> | 0.533 <sub>498/934</sub> | 0.837 <sub>2164/2586</sub> | 0.868 <sub>2587/2981</sub> | 0.872 <sub>2741/3144</sub> | 0.792 <sub>1139/1438</sub> |
| `excess_jumps_per_transition_one_rule` ↓ | 0.852 <sub>2471/2900</sub> | 0.837 <sub>2233/2669</sub> | 0.837 <sub>2164/2586</sub> | 0.868 <sub>2587/2981</sub> | 0.872 <sub>2741/3144</sub> | 0.792 <sub>1139/1438</sub> |
| `pages_with_columns` = | 290 <sub>290/600</sub> | 294 <sub>294/600</sub> | 288 <sub>288/600</sub> | 275 <sub>275/600</sub> | 293 <sub>293/600</sub> | 227 <sub>227/600</sub> |
| `transitions` = | 930 | 934 | 2586 | 2981 | 3144 | 1438 |

  params, the same for every model here: `COLUMN_buckets_counted=['artifact', 'text']`, `COLUMN_full_width_box_share=0.6`, `COLUMN_min_boxes_per_page=2`, `COLUMN_x_overlap_of_narrow_box=0.5`, `order_rule_one_rule=ours_top_down_left_right (forced)`

  `PP-DocLayoutV2` differs: `order_rule=model_rank`

  `PP-DocLayoutV3` differs: `order_rule=model_rank`

  `PP-DocLayout_plus-L` differs: `order_rule=ours_top_down_left_right: the model gives no rank`

  `docling-egret` differs: `order_rule=ours_top_down_left_right`

  `docling-heron` differs: `order_rule=ours_top_down_left_right`

  `yolox_l0.05` differs: `order_rule=ours_top_down_left_right`

**contour**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `artefacts_called_text` ↓ | 0.036 <sub>44/1232</sub> | 0.018 <sub>22/1232</sub> | 0.030 <sub>37/1232</sub> | 0.042 <sub>52/1232</sub> | 0.045 <sub>56/1232</sub> | 0.014 <sub>17/1232</sub> |
| `artefacts_cropped` ↓ | 0.069 <sub>85/1232</sub> | 0.075 <sub>92/1232</sub> | 0.132 <sub>163/1232</sub> | 0.108 <sub>133/1232</sub> | 0.113 <sub>139/1232</sub> | 0.113 <sub>139/1232</sub> |
| `artefacts_found` ↑ | 0.567 <sub>698/1232</sub> | 0.553 <sub>681/1232</sub> | 0.511 <sub>630/1232</sub> | 0.537 <sub>661/1232</sub> | 0.563 <sub>694/1232</sub> | 0.299 <sub>368/1232</sub> |
| `artefacts_merged` = | 0.304 <sub>375/1232</sub> | 0.293 <sub>361/1232</sub> | 0.344 <sub>424/1232</sub> | 0.320 <sub>394/1232</sub> | 0.297 <sub>366/1232</sub> | 0.322 <sub>397/1232</sub> |
| `artefacts_not_seen` ↓ | 0.067 <sub>82/1232</sub> | 0.121 <sub>149/1232</sub> | 0.060 <sub>74/1232</sub> | 0.057 <sub>70/1232</sub> | 0.056 <sub>69/1232</sub> | 0.314 <sub>387/1232</sub> |
| `assembly_order` ↑ | — | — | — | — | — | — |
| `label_errors` ↓ | 139 <sub>139/731</sub> | 113 <sub>113/705</sub> | — | — | — | — |
| `model_order` ↑ | — | — | — | — | — | — |
| `role_errors` ↓ | 33 <sub>33/731</sub> | 24 <sub>24/705</sub> | 40 <sub>40/669</sub> | 52 <sub>52/703</sub> | 54 <sub>54/731</sub> | 13 <sub>13/379</sub> |
| `sense_whole` ↑ | 0.524 <sub>646/1232</sub> | 0.494 <sub>608/1232</sub> | 0.433 <sub>534/1232</sub> | 0.473 <sub>583/1232</sub> | 0.489 <sub>602/1232</sub> | 0.237 <sub>292/1232</sub> |
| `text_furniture_found` ↑ | — | — | — | — | — | — |

- a dash: text and furniture NOT MARKED in this truth
- a dash: the two sides speak different label vocabularies; not compared
- a dash: truth carries no order: not marked on 600 of 600 pages

  params, the same for every model here: `COLUMN_buckets_counted=['artifact', 'text']`, `COLUMN_full_width_box_share=0.6`, `COLUMN_min_boxes_per_page=2`, `COLUMN_x_overlap_of_narrow_box=0.5`, `COVER_MATCH=0.75`, `SENSE_NEIGHBOUR=0.5`, `SENSE_WHOLE=0.9`, `TOL_PX=6.0`, `TOUCH=0.1`

**fitness**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `area_under_boxes` = | 0.574 <sub>1803024493/3143219854</sub> | 0.532 <sub>1671177053/3143219854</sub> | 0.576 <sub>1810246688/3143219854</sub> | 0.587 <sub>1845212945/3143219854</sub> | 0.582 <sub>1829499884/3143219854</sub> | 0.452 <sub>1419377277/3143219854</sub> |
| `boxes_per_page` = | 17.912 <sub>10747/600</sub> | 14.707 <sub>8824/600</sub> | 15.060 <sub>9036/600</sub> | 23.700 <sub>14220/600</sub> | 26.148 <sub>15689/600</sub> | 8.495 <sub>5097/600</sub> |
| `ink_as_picture` = | — | — | — | — | — | — |
| `ink_as_text` ↑ | — | — | — | — | — | — |
| `ink_junk` = | 0.036 <sub>26757759/739099410</sub> | 0.036 <sub>26757759/739099410</sub> | 0.036 <sub>26757759/739099410</sub> | 0.036 <sub>26757759/739099410</sub> | 0.036 <sub>26757759/739099410</sub> | 0.036 <sub>26757759/739099410</sub> |
| `ink_under_artefacts` = | 0.297 <sub>219183522/739099410</sub> | 0.281 <sub>207885090/739099410</sub> | 0.355 <sub>262702520/739099410</sub> | 0.333 <sub>245903479/739099410</sub> | 0.334 <sub>247183687/739099410</sub> | 0.234 <sub>173239528/739099410</sub> |
| `ink_under_boxes` ↑ | 0.727 <sub>537247851/739099410</sub> | 0.665 <sub>491613557/739099410</sub> | 0.745 <sub>550633038/739099410</sub> | 0.761 <sub>562593874/739099410</sub> | 0.754 <sub>557443399/739099410</sub> | 0.534 <sub>394361133/739099410</sub> |
| `ink_under_boxes_clean` ↑ | 0.751 <sub>535089502/712341651</sub> | 0.687 <sub>489721197/712341651</sub> | 0.769 <sub>548069179/712341651</sub> | 0.786 <sub>560132483/712341651</sub> | 0.780 <sub>555463036/712341651</sub> | 0.552 <sub>393074841/712341651</sub> |
| `median_box_area` = | 0.010 | 0.013 | 0.013 | 0.010 | 0.010 | 0.028 |
| `object_ink_preserved` ↑ | 0.894 <sub>149614306/167384248</sub> | 0.915 <sub>153165766/167384248</sub> | 0.945 <sub>158095780/167384248</sub> | 0.893 <sub>149507725/167384248</sub> | 0.945 <sub>158239797/167384248</sub> | 0.719 <sub>120330962/167384248</sub> |
| `objects_in_one_box` ↑ | 0.824 <sub>1014/1230</sub> | 0.786 <sub>967/1230</sub> | 0.774 <sub>952/1230</sub> | 0.843 <sub>1037/1230</sub> | 0.852 <sub>1048/1230</sub> | 0.528 <sub>649/1230</sub> |
| `objects_intact` ↑ | 0.828 <sub>1018/1230</sub> | 0.789 <sub>970/1230</sub> | 0.780 <sub>959/1230</sub> | 0.845 <sub>1039/1230</sub> | 0.853 <sub>1049/1230</sub> | 0.528 <sub>649/1230</sub> |
| `objects_left_as_text` ↓ | 0.070 <sub>86/1230</sub> | 0.046 <sub>56/1230</sub> | 0.049 <sub>60/1230</sub> | 0.084 <sub>103/1230</sub> | 0.085 <sub>105/1230</sub> | 0.032 <sub>39/1230</sub> |
| `objects_torn` ↓ | 0.103 <sub>127/1230</sub> | 0.139 <sub>171/1230</sub> | 0.089 <sub>109/1230</sub> | 0.101 <sub>124/1230</sub> | 0.103 <sub>127/1230</sub> | 0.337 <sub>415/1230</sub> |
| `objects_with_company` ↓ | 0.314 <sub>386/1230</sub> | 0.298 <sub>366/1230</sub> | 0.376 <sub>462/1230</sub> | 0.367 <sub>451/1230</sub> | 0.363 <sub>447/1230</sub> | 0.311 <sub>382/1230</sub> |

- a dash: this run read nothing: every block would leave as a picture, which is not a measurement of one

  params, the same for every model here: `GUTTER=0.5`, `GUTTER_BAND=0.2`, `JUNK_WIDTH=0.1`, `MID=0.2`, `MIN_SPREAD_RATIO=1.15`, `RULE_RUN=0.25`, `almost=0.95`, `bitten=0.8`, `dpi=[144]`, `edge_band=0.04`, `ink=160`, `intact=0.99`

**snapshot**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `empty` ↓ | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 16 <sub>16/78</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 17 <sub>17/79</sub> |
| `fingerprint_verified` = | 0 | 0 | 1 | 0 | 0 | 1 |
| `missing` ↓ | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/78</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/79</sub> |
| `values_present` = | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 78 <sub>78/78</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 79 <sub>79/79</sub> |

### atlas

**assembly**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `excess_jumps` ↓ | 0 | 0 | 2 | 2 | 2 | 0 |
| `excess_jumps_per_page` ↓ | 0.000 <sub>over 2/11 pages</sub> | 0.000 <sub>over 6/11 pages</sub> | 0.667 <sub>over 3/11 pages</sub> | 1.000 <sub>over 2/11 pages</sub> | 0.400 <sub>over 5/11 pages</sub> | 0.000 <sub>over 1/11 pages</sub> |
| `excess_jumps_per_transition` ↓ | 0.000 <sub>0/2</sub> | 0.000 <sub>0/5</sub> | 0.400 <sub>2/5</sub> | 0.667 <sub>2/3</sub> | 0.333 <sub>2/6</sub> | 0.000 <sub>0/1</sub> |
| `excess_jumps_per_transition_one_rule` ↓ | 0.333 <sub>1/3</sub> | 0.000 <sub>0/5</sub> | 0.400 <sub>2/5</sub> | 0.667 <sub>2/3</sub> | 0.333 <sub>2/6</sub> | 0.000 <sub>0/1</sub> |
| `pages_with_columns` = | 2 <sub>2/11</sub> | 5 <sub>5/11</sub> | 2 <sub>2/11</sub> | 1 <sub>1/11</sub> | 4 <sub>4/11</sub> | 1 <sub>1/11</sub> |
| `transitions` = | 2 | 5 | 5 | 3 | 6 | 1 |

  params, the same for every model here: `COLUMN_buckets_counted=['artifact', 'text']`, `COLUMN_full_width_box_share=0.6`, `COLUMN_min_boxes_per_page=2`, `COLUMN_x_overlap_of_narrow_box=0.5`, `order_rule_one_rule=ours_top_down_left_right (forced)`

  `PP-DocLayoutV2` differs: `order_rule=model_rank`

  `PP-DocLayoutV3` differs: `order_rule=model_rank`

  `PP-DocLayout_plus-L` differs: `order_rule=ours_top_down_left_right: the model gives no rank`

  `docling-egret` differs: `order_rule=ours_top_down_left_right`

  `docling-heron` differs: `order_rule=ours_top_down_left_right`

  `yolox_l0.05` differs: `order_rule=ours_top_down_left_right`

**contour**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `artefacts_called_text` ↓ | 0.062 <sub>1/16</sub> | 0.000 <sub>0/16</sub> | 0.000 <sub>0/16</sub> | 0.000 <sub>0/16</sub> | 0.000 <sub>0/16</sub> | 0.000 <sub>0/16</sub> |
| `artefacts_cropped` ↓ | 0.000 <sub>0/16</sub> | 0.062 <sub>1/16</sub> | 0.062 <sub>1/16</sub> | 0.000 <sub>0/16</sub> | 0.000 <sub>0/16</sub> | 0.000 <sub>0/16</sub> |
| `artefacts_found` ↑ | 0.750 <sub>12/16</sub> | 0.688 <sub>11/16</sub> | 0.875 <sub>14/16</sub> | 0.750 <sub>12/16</sub> | 0.875 <sub>14/16</sub> | 0.688 <sub>11/16</sub> |
| `artefacts_merged` = | 0.000 <sub>0/16</sub> | 0.125 <sub>2/16</sub> | 0.000 <sub>0/16</sub> | 0.250 <sub>4/16</sub> | 0.062 <sub>1/16</sub> | 0.125 <sub>2/16</sub> |
| `artefacts_not_seen` ↓ | 0.188 <sub>3/16</sub> | 0.125 <sub>2/16</sub> | 0.125 <sub>2/16</sub> | 0.000 <sub>0/16</sub> | 0.062 <sub>1/16</sub> | 0.188 <sub>3/16</sub> |
| `assembly_order` ↑ | 0.952 | 1.000 | 0.882 | 0.895 | 0.913 | 0.900 |
| `label_errors` ↓ | 11 <sub>11/25</sub> | 2 <sub>2/23</sub> | 0 <sub>0/22</sub> | — | — | — |
| `model_order` ↑ | 0.952 | 1.000 | — | — | — | — |
| `role_errors` ↓ | 9 <sub>9/25</sub> | 2 <sub>2/23</sub> | 0 <sub>0/22</sub> | 0 <sub>0/23</sub> | 5 <sub>5/26</sub> | 2 <sub>2/17</sub> |
| `sense_whole` ↑ | 0.750 <sub>12/16</sub> | 0.688 <sub>11/16</sub> | 0.812 <sub>13/16</sub> | 0.750 <sub>12/16</sub> | 0.875 <sub>14/16</sub> | 0.688 <sub>11/16</sub> |
| `text_furniture_found` ↑ | 1.000 <sub>12/12</sub> | 1.000 <sub>12/12</sub> | 0.667 <sub>8/12</sub> | 0.917 <sub>11/12</sub> | 1.000 <sub>12/12</sub> | 0.500 <sub>6/12</sub> |

- a dash: the model gives no rank (ours_top_down_left_right)
- a dash: the model gives no rank (ours_top_down_left_right: the model gives no rank)
- a dash: the two sides speak different label vocabularies; not compared

  params, the same for every model here: `COLUMN_buckets_counted=['artifact', 'text']`, `COLUMN_full_width_box_share=0.6`, `COLUMN_min_boxes_per_page=2`, `COLUMN_x_overlap_of_narrow_box=0.5`, `COVER_MATCH=0.75`, `SENSE_NEIGHBOUR=0.5`, `SENSE_WHOLE=0.9`, `TOL_PX=6.0`, `TOUCH=0.1`

**fitness**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `area_under_boxes` = | 0.456 <sub>7968897/17487360</sub> | 0.487 <sub>8510193/17487360</sub> | 0.594 <sub>10387954/17487360</sub> | 0.710 <sub>12418127/17487360</sub> | 0.501 <sub>8756519/17487360</sub> | 0.607 <sub>10610343/17487360</sub> |
| `boxes_per_page` = | 2.545 <sub>28/11</sub> | 2.455 <sub>27/11</sub> | 2.455 <sub>27/11</sub> | 2.636 <sub>29/11</sub> | 3.636 <sub>40/11</sub> | 1.636 <sub>18/11</sub> |
| `ink_as_picture` = | — | — | — | — | — | — |
| `ink_as_text` ↑ | — | — | — | — | — | — |
| `ink_junk` = | 0.000 <sub>0/1127438</sub> | 0.000 <sub>0/1127438</sub> | 0.000 <sub>0/1127438</sub> | 0.000 <sub>0/1127438</sub> | 0.000 <sub>0/1127438</sub> | 0.000 <sub>0/1127438</sub> |
| `ink_under_artefacts` = | 0.793 <sub>893981/1127438</sub> | 0.818 <sub>922394/1127438</sub> | 0.834 <sub>940356/1127438</sub> | 0.934 <sub>1053254/1127438</sub> | 0.854 <sub>963099/1127438</sub> | 0.833 <sub>939077/1127438</sub> |
| `ink_under_boxes` ↑ | 0.860 <sub>969214/1127438</sub> | 0.874 <sub>985726/1127438</sub> | 0.898 <sub>1012742/1127438</sub> | 0.989 <sub>1114659/1127438</sub> | 0.910 <sub>1026408/1127438</sub> | 0.881 <sub>993304/1127438</sub> |
| `ink_under_boxes_clean` ↑ | 0.860 <sub>969214/1127438</sub> | 0.874 <sub>985726/1127438</sub> | 0.898 <sub>1012742/1127438</sub> | 0.989 <sub>1114659/1127438</sub> | 0.910 <sub>1026408/1127438</sub> | 0.881 <sub>993304/1127438</sub> |
| `median_box_area` = | 0.092 | 0.084 | 0.099 | 0.123 | 0.023 | 0.389 |
| `object_ink_preserved` ↑ | 0.903 <sub>893972/989602</sub> | 0.932 <sub>922349/989602</sub> | 0.948 <sub>937895/989602</sub> | 1.000 <sub>989344/989602</sub> | 0.954 <sub>944195/989602</sub> | 0.942 <sub>932686/989602</sub> |
| `objects_in_one_box` ↑ | 0.062 <sub>1/16</sub> | 0.188 <sub>3/16</sub> | 0.125 <sub>2/16</sub> | 1.000 <sub>16/16</sub> | 0.562 <sub>9/16</sub> | 0.125 <sub>2/16</sub> |
| `objects_intact` ↑ | 0.062 <sub>1/16</sub> | 0.188 <sub>3/16</sub> | 0.125 <sub>2/16</sub> | 1.000 <sub>16/16</sub> | 0.562 <sub>9/16</sub> | 0.125 <sub>2/16</sub> |
| `objects_left_as_text` ↓ | 0.062 <sub>1/16</sub> | 0.000 <sub>0/16</sub> | 0.062 <sub>1/16</sub> | 0.000 <sub>0/16</sub> | 0.000 <sub>0/16</sub> | 0.000 <sub>0/16</sub> |
| `objects_torn` ↓ | 0.312 <sub>5/16</sub> | 0.312 <sub>5/16</sub> | 0.188 <sub>3/16</sub> | 0.000 <sub>0/16</sub> | 0.062 <sub>1/16</sub> | 0.438 <sub>7/16</sub> |
| `objects_with_company` ↓ | 0.000 <sub>0/16</sub> | 0.000 <sub>0/16</sub> | 0.000 <sub>0/16</sub> | 0.562 <sub>9/16</sub> | 0.125 <sub>2/16</sub> | 0.000 <sub>0/16</sub> |

- a dash: this run read nothing: every block would leave as a picture, which is not a measurement of one

  params, the same for every model here: `GUTTER=0.5`, `GUTTER_BAND=0.2`, `JUNK_WIDTH=0.1`, `MID=0.2`, `MIN_SPREAD_RATIO=1.15`, `RULE_RUN=0.25`, `almost=0.95`, `bitten=0.8`, `dpi=[144]`, `edge_band=0.04`, `ink=160`, `intact=0.99`

**snapshot**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `empty` ↓ | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 17 <sub>17/79</sub> |
| `fingerprint_verified` = | 0 | 0 | 0 | 0 | 0 | 1 |
| `missing` ↓ | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/79</sub> |
| `values_present` = | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 79 <sub>79/79</sub> |

### hard

**assembly**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `excess_jumps` ↓ | 193 | 214 | 526 | 547 | 577 | 221 |
| `excess_jumps_per_page` ↓ | 1.608 <sub>over 120/130 pages</sub> | 1.769 <sub>over 121/130 pages</sub> | 4.574 <sub>over 115/130 pages</sub> | 4.521 <sub>over 121/130 pages</sub> | 4.691 <sub>over 123/130 pages</sub> | 2.402 <sub>over 92/130 pages</sub> |
| `excess_jumps_per_transition` ↓ | 0.583 <sub>193/331</sub> | 0.610 <sub>214/351</sub> | 0.802 <sub>526/656</sub> | 0.820 <sub>547/667</sub> | 0.825 <sub>577/699</sub> | 0.747 <sub>221/296</sub> |
| `excess_jumps_per_transition_one_rule` ↓ | 0.829 <sub>669/807</sub> | 0.801 <sub>551/688</sub> | 0.802 <sub>526/656</sub> | 0.820 <sub>547/667</sub> | 0.825 <sub>577/699</sub> | 0.747 <sub>221/296</sub> |
| `pages_with_columns` = | 94 <sub>94/130</sub> | 94 <sub>94/130</sub> | 87 <sub>87/130</sub> | 87 <sub>87/130</sub> | 92 <sub>92/130</sub> | 63 <sub>63/130</sub> |
| `transitions` = | 331 | 351 | 656 | 667 | 699 | 296 |

  params, the same for every model here: `COLUMN_buckets_counted=['artifact', 'text']`, `COLUMN_full_width_box_share=0.6`, `COLUMN_min_boxes_per_page=2`, `COLUMN_x_overlap_of_narrow_box=0.5`, `order_rule_one_rule=ours_top_down_left_right (forced)`

  `PP-DocLayoutV2` differs: `order_rule=model_rank`

  `PP-DocLayoutV3` differs: `order_rule=model_rank`

  `PP-DocLayout_plus-L` differs: `order_rule=ours_top_down_left_right: the model gives no rank`

  `docling-egret` differs: `order_rule=ours_top_down_left_right`

  `docling-heron` differs: `order_rule=ours_top_down_left_right`

  `yolox_l0.05` differs: `order_rule=ours_top_down_left_right`

**contour**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `artefacts_called_text` ↓ | 0.029 <sub>21/736</sub> | 0.012 <sub>9/736</sub> | 0.031 <sub>23/736</sub> | 0.035 <sub>26/736</sub> | 0.042 <sub>31/736</sub> | 0.012 <sub>9/736</sub> |
| `artefacts_cropped` ↓ | 0.061 <sub>45/736</sub> | 0.053 <sub>39/736</sub> | 0.114 <sub>84/736</sub> | 0.083 <sub>61/736</sub> | 0.084 <sub>62/736</sub> | 0.076 <sub>56/736</sub> |
| `artefacts_found` ↑ | 0.429 <sub>316/736</sub> | 0.401 <sub>295/736</sub> | 0.357 <sub>263/736</sub> | 0.402 <sub>296/736</sub> | 0.431 <sub>317/736</sub> | 0.166 <sub>122/736</sub> |
| `artefacts_merged` = | 0.497 <sub>366/736</sub> | 0.476 <sub>350/736</sub> | 0.541 <sub>398/736</sub> | 0.507 <sub>373/736</sub> | 0.471 <sub>347/736</sub> | 0.515 <sub>379/736</sub> |
| `artefacts_not_seen` ↓ | 0.041 <sub>30/736</sub> | 0.120 <sub>88/736</sub> | 0.045 <sub>33/736</sub> | 0.038 <sub>28/736</sub> | 0.048 <sub>35/736</sub> | 0.288 <sub>212/736</sub> |
| `assembly_order` ↑ | 0.957 <sub>over 6/130 pages</sub> | 0.958 <sub>over 6/130 pages</sub> | 0.913 <sub>over 6/130 pages</sub> | 0.908 <sub>over 6/130 pages</sub> | 0.917 <sub>over 6/130 pages</sub> | 0.904 <sub>over 6/130 pages</sub> |
| `label_errors` ↓ | 75 <sub>75/375</sub> | 67 <sub>67/358</sub> | — | — | — | — |
| `model_order` ↑ | 0.957 <sub>over 6/130 pages</sub> | 0.958 <sub>over 6/130 pages</sub> | — | — | — | — |
| `role_errors` ↓ | 16 <sub>16/375</sub> | 17 <sub>17/358</sub> | 17 <sub>17/325</sub> | 19 <sub>19/354</sub> | 21 <sub>21/375</sub> | 5 <sub>5/165</sub> |
| `sense_whole` ↑ | 0.372 <sub>274/736</sub> | 0.340 <sub>250/736</sub> | 0.269 <sub>198/736</sub> | 0.337 <sub>248/736</sub> | 0.355 <sub>261/736</sub> | 0.109 <sub>80/736</sub> |
| `text_furniture_found` ↑ | 0.918 <sub>45/49</sub> <sub>over 6/130 pages</sub> | 0.939 <sub>46/49</sub> <sub>over 6/130 pages</sub> | 0.918 <sub>45/49</sub> <sub>over 6/130 pages</sub> | 0.857 <sub>42/49</sub> <sub>over 6/130 pages</sub> | 0.939 <sub>46/49</sub> <sub>over 6/130 pages</sub> | 0.796 <sub>39/49</sub> <sub>over 6/130 pages</sub> |

- a dash: the model gives no rank (ours_top_down_left_right)
- a dash: the model gives no rank (ours_top_down_left_right: the model gives no rank)
- a dash: the two sides speak different label vocabularies; not compared

  params, the same for every model here: `COLUMN_buckets_counted=['artifact', 'text']`, `COLUMN_full_width_box_share=0.6`, `COLUMN_min_boxes_per_page=2`, `COLUMN_x_overlap_of_narrow_box=0.5`, `COVER_MATCH=0.75`, `SENSE_NEIGHBOUR=0.5`, `SENSE_WHOLE=0.9`, `TOL_PX=6.0`, `TOUCH=0.1`

**fitness**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `area_under_boxes` = | 0.607 <sub>365956611/603386958</sub> | 0.556 <sub>335448178/603386958</sub> | 0.600 <sub>362002399/603386958</sub> | 0.613 <sub>369588930/603386958</sub> | 0.606 <sub>365898207/603386958</sub> | 0.466 <sub>281063201/603386958</sub> |
| `boxes_per_page` = | 21.015 <sub>2732/130</sub> | 17.354 <sub>2256/130</sub> | 17.723 <sub>2304/130</sub> | 27.277 <sub>3546/130</sub> | 29.508 <sub>3836/130</sub> | 10.246 <sub>1332/130</sub> |
| `ink_as_picture` = | — | — | — | — | — | — |
| `ink_as_text` ↑ | — | — | — | — | — | — |
| `ink_junk` = | 0.024 <sub>2323143/96454397</sub> | 0.024 <sub>2323143/96454397</sub> | 0.024 <sub>2323143/96454397</sub> | 0.024 <sub>2323143/96454397</sub> | 0.024 <sub>2323143/96454397</sub> | 0.024 <sub>2323143/96454397</sub> |
| `ink_under_artefacts` = | 0.254 <sub>24472007/96454397</sub> | 0.245 <sub>23627921/96454397</sub> | 0.313 <sub>30236405/96454397</sub> | 0.282 <sub>27158321/96454397</sub> | 0.283 <sub>27250792/96454397</sub> | 0.192 <sub>18522998/96454397</sub> |
| `ink_under_boxes` ↑ | 0.771 <sub>74357353/96454397</sub> | 0.698 <sub>67298678/96454397</sub> | 0.782 <sub>75471257/96454397</sub> | 0.791 <sub>76324624/96454397</sub> | 0.795 <sub>76657835/96454397</sub> | 0.554 <sub>53401221/96454397</sub> |
| `ink_under_boxes_clean` ↑ | 0.790 <sub>74338517/94131254</sub> | 0.715 <sub>67277234/94131254</sub> | 0.801 <sub>75445199/94131254</sub> | 0.810 <sub>76279004/94131254</sub> | 0.814 <sub>76616803/94131254</sub> | 0.567 <sub>53384887/94131254</sub> |
| `median_box_area` = | 0.011 | 0.013 | 0.014 | 0.011 | 0.011 | 0.031 |
| `object_ink_preserved` ↑ | 0.922 <sub>26637623/28887708</sub> | 0.883 <sub>25503180/28887708</sub> | 0.936 <sub>27048832/28887708</sub> | 0.933 <sub>26966397/28887708</sub> | 0.900 <sub>26005793/28887708</sub> | 0.697 <sub>20144631/28887708</sub> |
| `objects_in_one_box` ↑ | 0.887 <sub>651/734</sub> | 0.820 <sub>602/734</sub> | 0.831 <sub>610/734</sub> | 0.891 <sub>654/734</sub> | 0.883 <sub>648/734</sub> | 0.606 <sub>445/734</sub> |
| `objects_intact` ↑ | 0.888 <sub>652/734</sub> | 0.820 <sub>602/734</sub> | 0.834 <sub>612/734</sub> | 0.892 <sub>655/734</sub> | 0.883 <sub>648/734</sub> | 0.606 <sub>445/734</sub> |
| `objects_left_as_text` ↓ | 0.057 <sub>42/734</sub> | 0.037 <sub>27/734</sub> | 0.040 <sub>29/734</sub> | 0.074 <sub>54/734</sub> | 0.075 <sub>55/734</sub> | 0.033 <sub>24/734</sub> |
| `objects_torn` ↓ | 0.071 <sub>52/734</sub> | 0.129 <sub>95/734</sub> | 0.075 <sub>55/734</sub> | 0.074 <sub>54/734</sub> | 0.090 <sub>66/734</sub> | 0.311 <sub>228/734</sub> |
| `objects_with_company` ↓ | 0.518 <sub>380/734</sub> | 0.480 <sub>352/734</sub> | 0.579 <sub>425/734</sub> | 0.586 <sub>430/734</sub> | 0.571 <sub>419/734</sub> | 0.497 <sub>365/734</sub> |

- a dash: this run read nothing: every block would leave as a picture, which is not a measurement of one

  params, the same for every model here: `GUTTER=0.5`, `GUTTER_BAND=0.2`, `JUNK_WIDTH=0.1`, `MID=0.2`, `MIN_SPREAD_RATIO=1.15`, `RULE_RUN=0.25`, `almost=0.95`, `bitten=0.8`, `dpi=[144]`, `edge_band=0.04`, `ink=160`, `intact=0.99`

**snapshot**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `empty` ↓ | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 17 <sub>17/79</sub> |
| `fingerprint_verified` = | 0 | 0 | 0 | 0 | 0 | 1 |
| `missing` ↓ | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/79</sub> |
| `values_present` = | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 79 <sub>79/79</sub> |

### hard36

**assembly**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `excess_jumps` ↓ | 87 | 83 | 159 | 149 | 139 | 90 |
| `excess_jumps_per_page` ↓ | 2.806 <sub>over 31/36 pages</sub> | 2.677 <sub>over 31/36 pages</sub> | 5.129 <sub>over 31/36 pages</sub> | 4.515 <sub>over 33/36 pages</sub> | 4.088 <sub>over 34/36 pages</sub> | 3.214 <sub>over 28/36 pages</sub> |
| `excess_jumps_per_transition` ↓ | 0.685 <sub>87/127</sub> | 0.680 <sub>83/122</sub> | 0.787 <sub>159/202</sub> | 0.801 <sub>149/186</sub> | 0.799 <sub>139/174</sub> | 0.789 <sub>90/114</sub> |
| `excess_jumps_per_transition_one_rule` ↓ | 0.813 <sub>174/214</sub> | 0.791 <sub>148/187</sub> | 0.787 <sub>159/202</sub> | 0.801 <sub>149/186</sub> | 0.799 <sub>139/174</sub> | 0.789 <sub>90/114</sub> |
| `pages_with_columns` = | 27 <sub>27/36</sub> | 26 <sub>26/36</sub> | 27 <sub>27/36</sub> | 27 <sub>27/36</sub> | 26 <sub>26/36</sub> | 21 <sub>21/36</sub> |
| `transitions` = | 127 | 122 | 202 | 186 | 174 | 114 |

  params, the same for every model here: `COLUMN_buckets_counted=['artifact', 'text']`, `COLUMN_full_width_box_share=0.6`, `COLUMN_min_boxes_per_page=2`, `COLUMN_x_overlap_of_narrow_box=0.5`, `order_rule_one_rule=ours_top_down_left_right (forced)`

  `PP-DocLayoutV2` differs: `order_rule=model_rank`

  `PP-DocLayoutV3` differs: `order_rule=model_rank`

  `PP-DocLayout_plus-L` differs: `order_rule=ours_top_down_left_right: the model gives no rank`

  `docling-egret` differs: `order_rule=ours_top_down_left_right`

  `docling-heron` differs: `order_rule=ours_top_down_left_right`

  `yolox_l0.05` differs: `order_rule=ours_top_down_left_right`

**contour**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `artefacts_called_text` ↓ | 0.030 <sub>12/403</sub> | 0.002 <sub>1/403</sub> | 0.032 <sub>13/403</sub> | 0.042 <sub>17/403</sub> | 0.035 <sub>14/403</sub> | 0.010 <sub>4/403</sub> |
| `artefacts_cropped` ↓ | 0.052 <sub>21/403</sub> | 0.045 <sub>18/403</sub> | 0.107 <sub>43/403</sub> | 0.050 <sub>20/403</sub> | 0.060 <sub>24/403</sub> | 0.050 <sub>20/403</sub> |
| `artefacts_found` ↑ | 0.199 <sub>80/403</sub> | 0.206 <sub>83/403</sub> | 0.176 <sub>71/403</sub> | 0.191 <sub>77/403</sub> | 0.218 <sub>88/403</sub> | 0.094 <sub>38/403</sub> |
| `artefacts_merged` = | 0.737 <sub>297/403</sub> | 0.667 <sub>269/403</sub> | 0.720 <sub>290/403</sub> | 0.670 <sub>270/403</sub> | 0.705 <sub>284/403</sub> | 0.653 <sub>263/403</sub> |
| `artefacts_not_seen` ↓ | 0.032 <sub>13/403</sub> | 0.139 <sub>56/403</sub> | 0.037 <sub>15/403</sub> | 0.092 <sub>37/403</sub> | 0.055 <sub>22/403</sub> | 0.226 <sub>91/403</sub> |
| `assembly_order` ↑ | — | — | — | — | — | — |
| `label_errors` ↓ | 8 <sub>8/89</sub> | 11 <sub>11/96</sub> | — | — | — | — |
| `model_order` ↑ | — | — | — | — | — | — |
| `role_errors` ↓ | 1 <sub>1/89</sub> | 5 <sub>5/96</sub> | 3 <sub>3/82</sub> | 9 <sub>9/94</sub> | 6 <sub>6/102</sub> | 0 <sub>0/46</sub> |
| `sense_whole` ↑ | 0.149 <sub>60/403</sub> | 0.146 <sub>59/403</sub> | 0.104 <sub>42/403</sub> | 0.146 <sub>59/403</sub> | 0.146 <sub>59/403</sub> | 0.062 <sub>25/403</sub> |
| `text_furniture_found` ↑ | — | — | — | — | — | — |

- a dash: text and furniture NOT MARKED in this truth
- a dash: the two sides speak different label vocabularies; not compared
- a dash: truth carries no order: not_said on 36 of 36 pages

  params, the same for every model here: `COLUMN_buckets_counted=['artifact', 'text']`, `COLUMN_full_width_box_share=0.6`, `COLUMN_min_boxes_per_page=2`, `COLUMN_x_overlap_of_narrow_box=0.5`, `COVER_MATCH=0.75`, `SENSE_NEIGHBOUR=0.5`, `SENSE_WHOLE=0.9`, `TOL_PX=6.0`, `TOUCH=0.1`

**fitness**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `area_under_boxes` = | 0.604 <sub>47926624/79298034</sub> | 0.540 <sub>42784210/79298034</sub> | 0.573 <sub>45439407/79298034</sub> | 0.574 <sub>45500090/79298034</sub> | 0.601 <sub>47662762/79298034</sub> | 0.496 <sub>39339941/79298034</sub> |
| `boxes_per_page` = | 22.000 <sub>792/36</sub> | 18.417 <sub>663/36</sub> | 19.083 <sub>687/36</sub> | 31.944 <sub>1150/36</sub> | 32.000 <sub>1152/36</sub> | 11.278 <sub>406/36</sub> |
| `ink_as_picture` = | — | — | — | — | — | — |
| `ink_as_text` ↑ | — | — | — | — | — | — |
| `ink_junk` = | 0.029 <sub>407228/13857314</sub> | 0.029 <sub>407228/13857314</sub> | 0.029 <sub>407228/13857314</sub> | 0.029 <sub>407228/13857314</sub> | 0.029 <sub>407228/13857314</sub> | 0.029 <sub>407228/13857314</sub> |
| `ink_under_artefacts` = | 0.303 <sub>4193178/13857314</sub> | 0.289 <sub>4004842/13857314</sub> | 0.317 <sub>4394075/13857314</sub> | 0.304 <sub>4210109/13857314</sub> | 0.335 <sub>4646699/13857314</sub> | 0.262 <sub>3625712/13857314</sub> |
| `ink_under_boxes` ↑ | 0.757 <sub>10495785/13857314</sub> | 0.700 <sub>9700902/13857314</sub> | 0.734 <sub>10175878/13857314</sub> | 0.752 <sub>10414007/13857314</sub> | 0.773 <sub>10718079/13857314</sub> | 0.610 <sub>8449863/13857314</sub> |
| `ink_under_boxes_clean` ↑ | 0.779 <sub>10475009/13450086</sub> | 0.721 <sub>9693175/13450086</sub> | 0.756 <sub>10169710/13450086</sub> | 0.774 <sub>10405280/13450086</sub> | 0.795 <sub>10694336/13450086</sub> | 0.628 <sub>8441329/13450086</sub> |
| `median_box_area` = | 0.012 | 0.012 | 0.013 | 0.007 | 0.009 | 0.026 |
| `object_ink_preserved` ↑ | 0.948 <sub>5527339/5828260</sub> | 0.899 <sub>5240006/5828260</sub> | 0.948 <sub>5527880/5828260</sub> | 0.916 <sub>5338682/5828260</sub> | 0.949 <sub>5532404/5828260</sub> | 0.821 <sub>4785188/5828260</sub> |
| `objects_in_one_box` ↑ | 0.908 <sub>365/402</sub> | 0.841 <sub>338/402</sub> | 0.886 <sub>356/402</sub> | 0.848 <sub>341/402</sub> | 0.896 <sub>360/402</sub> | 0.716 <sub>288/402</sub> |
| `objects_intact` ↑ | 0.908 <sub>365/402</sub> | 0.841 <sub>338/402</sub> | 0.886 <sub>356/402</sub> | 0.848 <sub>341/402</sub> | 0.896 <sub>360/402</sub> | 0.716 <sub>288/402</sub> |
| `objects_left_as_text` ↓ | 0.052 <sub>21/402</sub> | 0.030 <sub>12/402</sub> | 0.042 <sub>17/402</sub> | 0.082 <sub>33/402</sub> | 0.082 <sub>33/402</sub> | 0.045 <sub>18/402</sub> |
| `objects_torn` ↓ | 0.070 <sub>28/402</sub> | 0.142 <sub>57/402</sub> | 0.070 <sub>28/402</sub> | 0.134 <sub>54/402</sub> | 0.092 <sub>37/402</sub> | 0.244 <sub>98/402</sub> |
| `objects_with_company` ↓ | 0.769 <sub>309/402</sub> | 0.692 <sub>278/402</sub> | 0.774 <sub>311/402</sub> | 0.729 <sub>293/402</sub> | 0.784 <sub>315/402</sub> | 0.659 <sub>265/402</sub> |

- a dash: this run read nothing: every block would leave as a picture, which is not a measurement of one

  params, the same for every model here: `GUTTER=0.5`, `GUTTER_BAND=0.2`, `JUNK_WIDTH=0.1`, `MID=0.2`, `MIN_SPREAD_RATIO=1.15`, `RULE_RUN=0.25`, `almost=0.95`, `bitten=0.8`, `dpi=[144]`, `edge_band=0.04`, `ink=160`, `intact=0.99`

**snapshot**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `empty` ↓ | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 17 <sub>17/79</sub> |
| `fingerprint_verified` = | 0 | 0 | 0 | 0 | 0 | 1 |
| `missing` ↓ | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/79</sub> |
| `values_present` = | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 79 <sub>79/79</sub> |

### katalog

**assembly**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `excess_jumps` ↓ | 0 | 347 | 0 | 2 | 5 | — |
| `excess_jumps_per_page` ↓ | 0.000 <sub>over 1/11 pages</sub> | 69.400 <sub>over 5/11 pages</sub> | 0.000 <sub>over 2/11 pages</sub> | 0.400 <sub>over 5/11 pages</sub> | 1.250 <sub>over 4/11 pages</sub> | — |
| `excess_jumps_per_transition` ↓ | — | 0.967 <sub>347/359</sub> | 0.000 <sub>0/13</sub> | 0.077 <sub>2/26</sub> | 0.250 <sub>5/20</sub> | — |
| `excess_jumps_per_transition_one_rule` ↓ | — | 0.967 <sub>348/360</sub> | 0.000 <sub>0/13</sub> | 0.077 <sub>2/26</sub> | 0.250 <sub>5/20</sub> | — |
| `pages_with_columns` = | 0 <sub>0/11</sub> | 4 <sub>4/11</sub> | 1 <sub>1/11</sub> | 5 <sub>5/11</sub> | 4 <sub>4/11</sub> | 0 <sub>0/11</sub> |
| `transitions` = | 0 | 359 | 13 | 26 | 20 | 0 |

- a dash: no page gathered two counted boxes: nothing to jump between
- a dash: the quantity is UNDEFINED: not one of the 11 pages gathered 2 counted boxes (counted in all 1, out of the count 34 full-width and 16 of other buckets) — nothing to jump between. This is NOT zero jumps.

  params, the same for every model here: `COLUMN_buckets_counted=['artifact', 'text']`, `COLUMN_full_width_box_share=0.6`, `COLUMN_min_boxes_per_page=2`, `COLUMN_x_overlap_of_narrow_box=0.5`, `order_rule_one_rule=ours_top_down_left_right (forced)`

  `PP-DocLayoutV2` differs: `order_rule=model_rank`

  `PP-DocLayoutV3` differs: `order_rule=model_rank`

  `PP-DocLayout_plus-L` differs: `order_rule=ours_top_down_left_right: the model gives no rank`

  `docling-egret` differs: `order_rule=ours_top_down_left_right`

  `docling-heron` differs: `order_rule=ours_top_down_left_right`

  `yolox_l0.05` differs: `order_rule=ours_top_down_left_right`

**contour**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `artefacts_called_text` ↓ | 0.000 <sub>0/13</sub> | 0.000 <sub>0/13</sub> | 0.000 <sub>0/13</sub> | 0.077 <sub>1/13</sub> | 0.000 <sub>0/13</sub> | 0.000 <sub>0/13</sub> |
| `artefacts_cropped` ↓ | 0.000 <sub>0/13</sub> | 0.000 <sub>0/13</sub> | 0.000 <sub>0/13</sub> | 0.000 <sub>0/13</sub> | 0.000 <sub>0/13</sub> | 0.385 <sub>5/13</sub> |
| `artefacts_found` ↑ | 0.846 <sub>11/13</sub> | 0.846 <sub>11/13</sub> | 0.769 <sub>10/13</sub> | 0.538 <sub>7/13</sub> | 0.462 <sub>6/13</sub> | 0.308 <sub>4/13</sub> |
| `artefacts_merged` = | 0.154 <sub>2/13</sub> | 0.000 <sub>0/13</sub> | 0.154 <sub>2/13</sub> | 0.000 <sub>0/13</sub> | 0.000 <sub>0/13</sub> | 0.000 <sub>0/13</sub> |
| `artefacts_not_seen` ↓ | 0.000 <sub>0/13</sub> | 0.154 <sub>2/13</sub> | 0.077 <sub>1/13</sub> | 0.385 <sub>5/13</sub> | 0.538 <sub>7/13</sub> | 0.154 <sub>2/13</sub> |
| `assembly_order` ↑ | 0.989 | 0.939 | 0.953 | 0.944 | 0.961 | 0.936 |
| `label_errors` ↓ | 3 <sub>3/60</sub> | 6 <sub>6/61</sub> | 3 <sub>3/53</sub> | — | — | — |
| `model_order` ↑ | 0.989 | 0.939 | — | — | — | — |
| `role_errors` ↓ | 0 <sub>0/60</sub> | 2 <sub>2/61</sub> | 0 <sub>0/53</sub> | 2 <sub>2/57</sub> | 0 <sub>0/59</sub> | 1 <sub>1/37</sub> |
| `sense_whole` ↑ | 0.846 <sub>11/13</sub> | 0.846 <sub>11/13</sub> | 0.769 <sub>10/13</sub> | 0.538 <sub>7/13</sub> | 0.462 <sub>6/13</sub> | 0.462 <sub>6/13</sub> |
| `text_furniture_found` ↑ | 0.891 <sub>49/55</sub> | 0.909 <sub>50/55</sub> | 0.782 <sub>43/55</sub> | 0.891 <sub>49/55</sub> | 0.964 <sub>53/55</sub> | 0.600 <sub>33/55</sub> |

- a dash: the model gives no rank (ours_top_down_left_right)
- a dash: the model gives no rank (ours_top_down_left_right: the model gives no rank)
- a dash: the two sides speak different label vocabularies; not compared

  params, the same for every model here: `COLUMN_buckets_counted=['artifact', 'text']`, `COLUMN_full_width_box_share=0.6`, `COLUMN_min_boxes_per_page=2`, `COLUMN_x_overlap_of_narrow_box=0.5`, `COVER_MATCH=0.75`, `SENSE_NEIGHBOUR=0.5`, `SENSE_WHOLE=0.9`, `TOL_PX=6.0`, `TOUCH=0.1`

**fitness**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `area_under_boxes` = | 0.670 <sub>11919182/17803104</sub> | 0.646 <sub>11504570/17803104</sub> | 0.633 <sub>11260854/17803104</sub> | 0.502 <sub>8938137/17803104</sub> | 0.505 <sub>8995853/17803104</sub> | 0.615 <sub>10940984/17803104</sub> |
| `boxes_per_page` = | 5.636 <sub>62/11</sub> | 44.909 <sub>494/11</sub> | 6.273 <sub>69/11</sub> | 11.727 <sub>129/11</sub> | 8.545 <sub>94/11</sub> | 4.636 <sub>51/11</sub> |
| `ink_as_picture` = | — | — | — | — | — | — |
| `ink_as_text` ↑ | — | — | — | — | — | — |
| `ink_junk` = | 0.045 <sub>58486/1288204</sub> | 0.045 <sub>58486/1288204</sub> | 0.045 <sub>58486/1288204</sub> | 0.045 <sub>58486/1288204</sub> | 0.045 <sub>58486/1288204</sub> | 0.045 <sub>58486/1288204</sub> |
| `ink_under_artefacts` = | 0.610 <sub>785842/1288204</sub> | 0.565 <sub>727919/1288204</sub> | 0.456 <sub>587618/1288204</sub> | 0.232 <sub>298727/1288204</sub> | 0.340 <sub>437845/1288204</sub> | 0.467 <sub>601961/1288204</sub> |
| `ink_under_boxes` ↑ | 0.967 <sub>1246014/1288204</sub> | 0.924 <sub>1190444/1288204</sub> | 0.965 <sub>1243512/1288204</sub> | 0.867 <sub>1117305/1288204</sub> | 0.904 <sub>1164323/1288204</sub> | 0.880 <sub>1133679/1288204</sub> |
| `ink_under_boxes_clean` ↑ | 0.974 <sub>1197423/1229718</sub> | 0.928 <sub>1141634/1229718</sub> | 0.972 <sub>1195382/1229718</sub> | 0.909 <sub>1117305/1229718</sub> | 0.907 <sub>1115883/1229718</sub> | 0.882 <sub>1084222/1229718</sub> |
| `median_box_area` = | 0.002 | 0.001 | 0.035 | 0.001 | 0.044 | 0.050 |
| `object_ink_preserved` ↑ | 1.000 <sub>782395/782450</sub> | 0.925 <sub>723781/782450</sub> | 0.746 <sub>583683/782450</sub> | 0.380 <sub>297618/782450</sub> | 0.556 <sub>434907/782450</sub> | 0.748 <sub>585542/782450</sub> |
| `objects_in_one_box` ↑ | 1.000 <sub>13/13</sub> | 0.846 <sub>11/13</sub> | 0.923 <sub>12/13</sub> | 0.538 <sub>7/13</sub> | 0.462 <sub>6/13</sub> | 0.231 <sub>3/13</sub> |
| `objects_intact` ↑ | 1.000 <sub>13/13</sub> | 0.846 <sub>11/13</sub> | 0.923 <sub>12/13</sub> | 0.538 <sub>7/13</sub> | 0.462 <sub>6/13</sub> | 0.231 <sub>3/13</sub> |
| `objects_left_as_text` ↓ | 0.000 <sub>0/13</sub> | 0.000 <sub>0/13</sub> | 0.077 <sub>1/13</sub> | 0.308 <sub>4/13</sub> | 0.154 <sub>2/13</sub> | 0.000 <sub>0/13</sub> |
| `objects_torn` ↓ | 0.000 <sub>0/13</sub> | 0.154 <sub>2/13</sub> | 0.077 <sub>1/13</sub> | 0.462 <sub>6/13</sub> | 0.538 <sub>7/13</sub> | 0.462 <sub>6/13</sub> |
| `objects_with_company` ↓ | 0.154 <sub>2/13</sub> | 0.000 <sub>0/13</sub> | 0.154 <sub>2/13</sub> | 0.154 <sub>2/13</sub> | 0.000 <sub>0/13</sub> | 0.000 <sub>0/13</sub> |

- a dash: this run read nothing: every block would leave as a picture, which is not a measurement of one

  params, the same for every model here: `GUTTER=0.5`, `GUTTER_BAND=0.2`, `JUNK_WIDTH=0.1`, `MID=0.2`, `MIN_SPREAD_RATIO=1.15`, `RULE_RUN=0.25`, `almost=0.95`, `bitten=0.8`, `dpi=[144]`, `edge_band=0.04`, `ink=160`, `intact=0.99`

**snapshot**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `empty` ↓ | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 17 <sub>17/79</sub> |
| `fingerprint_verified` = | 0 | 0 | 0 | 0 | 0 | 1 |
| `missing` ↓ | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/79</sub> |
| `values_present` = | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 79 <sub>79/79</sub> |

### matematika

**assembly**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `excess_jumps` ↓ | 10 | 10 | 10 | 0 | 10 | 0 |
| `excess_jumps_per_page` ↓ | 1.250 <sub>over 8/12 pages</sub> | 1.250 <sub>over 8/12 pages</sub> | 1.429 <sub>over 7/12 pages</sub> | 0.000 <sub>over 4/12 pages</sub> | 2.000 <sub>over 5/12 pages</sub> | 0.000 <sub>over 2/12 pages</sub> |
| `excess_jumps_per_transition` ↓ | 0.909 <sub>10/11</sub> | 0.909 <sub>10/11</sub> | 0.909 <sub>10/11</sub> | — | 0.909 <sub>10/11</sub> | — |
| `excess_jumps_per_transition_one_rule` ↓ | 0.909 <sub>10/11</sub> | 0.909 <sub>10/11</sub> | 0.909 <sub>10/11</sub> | — | 0.909 <sub>10/11</sub> | — |
| `pages_with_columns` = | 1 <sub>1/12</sub> | 1 <sub>1/12</sub> | 1 <sub>1/12</sub> | 0 <sub>0/12</sub> | 1 <sub>1/12</sub> | 0 <sub>0/12</sub> |
| `transitions` = | 11 | 11 | 11 | 0 | 11 | 0 |

- a dash: no page gathered two counted boxes: nothing to jump between

  params, the same for every model here: `COLUMN_buckets_counted=['artifact', 'text']`, `COLUMN_full_width_box_share=0.6`, `COLUMN_min_boxes_per_page=2`, `COLUMN_x_overlap_of_narrow_box=0.5`, `order_rule_one_rule=ours_top_down_left_right (forced)`

  `PP-DocLayoutV2` differs: `order_rule=model_rank`

  `PP-DocLayoutV3` differs: `order_rule=model_rank`

  `PP-DocLayout_plus-L` differs: `order_rule=ours_top_down_left_right: the model gives no rank`

  `docling-egret` differs: `order_rule=ours_top_down_left_right`

  `docling-heron` differs: `order_rule=ours_top_down_left_right`

  `yolox_l0.05` differs: `order_rule=ours_top_down_left_right`

**contour**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `artefacts_called_text` ↓ | 0.074 <sub>2/27</sub> | 0.000 <sub>0/27</sub> | 0.037 <sub>1/27</sub> | 0.000 <sub>0/27</sub> | 0.148 <sub>4/27</sub> | 0.000 <sub>0/27</sub> |
| `artefacts_cropped` ↓ | 0.037 <sub>1/27</sub> | 0.000 <sub>0/27</sub> | 0.481 <sub>13/27</sub> | 0.074 <sub>2/27</sub> | 0.000 <sub>0/27</sub> | 0.000 <sub>0/27</sub> |
| `artefacts_found` ↑ | 0.704 <sub>19/27</sub> | 0.741 <sub>20/27</sub> | 0.778 <sub>21/27</sub> | 0.111 <sub>3/27</sub> | 0.111 <sub>3/27</sub> | 0.000 <sub>0/27</sub> |
| `artefacts_merged` = | 0.074 <sub>2/27</sub> | 0.074 <sub>2/27</sub> | 0.370 <sub>10/27</sub> | 0.481 <sub>13/27</sub> | 0.667 <sub>18/27</sub> | 0.000 <sub>0/27</sub> |
| `artefacts_not_seen` ↓ | 0.148 <sub>4/27</sub> | 0.185 <sub>5/27</sub> | 0.000 <sub>0/27</sub> | 0.148 <sub>4/27</sub> | 0.074 <sub>2/27</sub> | 1.000 <sub>27/27</sub> |
| `assembly_order` ↑ | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| `label_errors` ↓ | 3 <sub>3/125</sub> | 3 <sub>3/124</sub> | — | — | — | — |
| `model_order` ↑ | 1.000 | 1.000 | — | — | — | — |
| `role_errors` ↓ | 2 <sub>2/125</sub> | 0 <sub>0/124</sub> | 1 <sub>1/126</sub> | 0 <sub>0/100</sub> | 13 <sub>13/119</sub> | 0 <sub>0/97</sub> |
| `sense_whole` ↑ | 0.667 <sub>18/27</sub> | 0.741 <sub>20/27</sub> | 0.111 <sub>3/27</sub> | 0.296 <sub>8/27</sub> | 0.111 <sub>3/27</sub> | 0.000 <sub>0/27</sub> |
| `text_furniture_found` ↑ | 1.000 <sub>104/104</sub> | 1.000 <sub>104/104</sub> | 1.000 <sub>104/104</sub> | 0.933 <sub>97/104</sub> | 0.990 <sub>103/104</sub> | 0.933 <sub>97/104</sub> |

- a dash: the model gives no rank (ours_top_down_left_right)
- a dash: the model gives no rank (ours_top_down_left_right: the model gives no rank)
- a dash: the two sides speak different label vocabularies; not compared

  params, the same for every model here: `COLUMN_buckets_counted=['artifact', 'text']`, `COLUMN_full_width_box_share=0.6`, `COLUMN_min_boxes_per_page=2`, `COLUMN_x_overlap_of_narrow_box=0.5`, `COVER_MATCH=0.75`, `SENSE_NEIGHBOUR=0.5`, `SENSE_WHOLE=0.9`, `TOL_PX=6.0`, `TOUCH=0.1`

**fitness**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `area_under_boxes` = | 0.493 <sub>7330150/14871168</sub> | 0.509 <sub>7568275/14871168</sub> | 0.463 <sub>6890698/14871168</sub> | 0.479 <sub>7125381/14871168</sub> | 0.474 <sub>7053727/14871168</sub> | 0.413 <sub>6143485/14871168</sub> |
| `boxes_per_page` = | 11.417 <sub>137/12</sub> | 14.417 <sub>173/12</sub> | 10.833 <sub>130/12</sub> | 13.417 <sub>161/12</sub> | 14.083 <sub>169/12</sub> | 9.750 <sub>117/12</sub> |
| `ink_as_picture` = | — | — | — | — | — | — |
| `ink_as_text` ↑ | — | — | — | — | — | — |
| `ink_junk` = | 0.000 <sub>0/1830374</sub> | 0.000 <sub>0/1830374</sub> | 0.000 <sub>0/1830374</sub> | 0.000 <sub>0/1830374</sub> | 0.000 <sub>0/1830374</sub> | 0.000 <sub>0/1830374</sub> |
| `ink_under_artefacts` = | 0.014 <sub>24744/1830374</sub> | 0.017 <sub>31430/1830374</sub> | 0.016 <sub>29446/1830374</sub> | 0.016 <sub>29154/1830374</sub> | 0.016 <sub>28807/1830374</sub> | 0.000 <sub>0/1830374</sub> |
| `ink_under_boxes` ↑ | 0.994 <sub>1819435/1830374</sub> | 0.994 <sub>1820031/1830374</sub> | 0.993 <sub>1818237/1830374</sub> | 0.992 <sub>1816455/1830374</sub> | 0.995 <sub>1820990/1830374</sub> | 0.956 <sub>1749063/1830374</sub> |
| `ink_under_boxes_clean` ↑ | 0.994 <sub>1819435/1830374</sub> | 0.994 <sub>1820031/1830374</sub> | 0.993 <sub>1818237/1830374</sub> | 0.992 <sub>1816455/1830374</sub> | 0.995 <sub>1820990/1830374</sub> | 0.956 <sub>1749063/1830374</sub> |
| `median_box_area` = | 0.041 | 0.039 | 0.039 | 0.038 | 0.037 | 0.036 |
| `object_ink_preserved` ↑ | 0.746 <sub>24672/33072</sub> | 0.948 <sub>31360/33072</sub> | 0.887 <sub>29335/33072</sub> | 0.855 <sub>28267/33072</sub> | 0.867 <sub>28664/33072</sub> | 0.000 <sub>0/33072</sub> |
| `objects_in_one_box` ↑ | 0.741 <sub>20/27</sub> | 0.815 <sub>22/27</sub> | 0.704 <sub>19/27</sub> | 0.852 <sub>23/27</sub> | 0.741 <sub>20/27</sub> | 0.000 <sub>0/27</sub> |
| `objects_intact` ↑ | 0.741 <sub>20/27</sub> | 0.815 <sub>22/27</sub> | 0.704 <sub>19/27</sub> | 0.852 <sub>23/27</sub> | 0.741 <sub>20/27</sub> | 0.000 <sub>0/27</sub> |
| `objects_left_as_text` ↓ | 0.037 <sub>1/27</sub> | 0.000 <sub>0/27</sub> | 0.037 <sub>1/27</sub> | 0.000 <sub>0/27</sub> | 0.222 <sub>6/27</sub> | 0.000 <sub>0/27</sub> |
| `objects_torn` ↓ | 0.222 <sub>6/27</sub> | 0.148 <sub>4/27</sub> | 0.074 <sub>2/27</sub> | 0.148 <sub>4/27</sub> | 0.222 <sub>6/27</sub> | 1.000 <sub>27/27</sub> |
| `objects_with_company` ↓ | 0.074 <sub>2/27</sub> | 0.074 <sub>2/27</sub> | 0.407 <sub>11/27</sub> | 0.519 <sub>14/27</sub> | 0.667 <sub>18/27</sub> | 0.000 <sub>0/27</sub> |

- a dash: this run read nothing: every block would leave as a picture, which is not a measurement of one

  params, the same for every model here: `GUTTER=0.5`, `GUTTER_BAND=0.2`, `JUNK_WIDTH=0.1`, `MID=0.2`, `MIN_SPREAD_RATIO=1.15`, `RULE_RUN=0.25`, `almost=0.95`, `bitten=0.8`, `dpi=[144]`, `edge_band=0.04`, `ink=160`, `intact=0.99`

**snapshot**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `empty` ↓ | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 17 <sub>17/79</sub> |
| `fingerprint_verified` = | 0 | 0 | 0 | 0 | 0 | 1 |
| `missing` ↓ | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/79</sub> |
| `values_present` = | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 79 <sub>79/79</sub> |

### slovar

**assembly**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `excess_jumps` ↓ | 130 | 23 | 214 | 640 | 475 | 431 |
| `excess_jumps_per_page` ↓ | 10.833 <sub>over 12/13 pages</sub> | 2.091 <sub>over 11/13 pages</sub> | 26.750 <sub>over 8/13 pages</sub> | 53.333 <sub>over 12/13 pages</sub> | 36.538 | 35.917 <sub>over 12/13 pages</sub> |
| `excess_jumps_per_transition` ↓ | 0.867 <sub>130/150</sub> | 0.548 <sub>23/42</sub> | 0.955 <sub>214/224</sub> | 0.967 <sub>640/662</sub> | 0.956 <sub>475/497</sub> | 0.958 <sub>431/450</sub> |
| `excess_jumps_per_transition_one_rule` ↓ | 0.960 <sub>479/499</sub> | 0.961 <sub>466/485</sub> | 0.955 <sub>214/224</sub> | 0.967 <sub>640/662</sub> | 0.956 <sub>475/497</sub> | 0.958 <sub>431/450</sub> |
| `pages_with_columns` = | 12 <sub>12/13</sub> | 11 <sub>11/13</sub> | 8 <sub>8/13</sub> | 12 <sub>12/13</sub> | 13 <sub>13/13</sub> | 12 <sub>12/13</sub> |
| `transitions` = | 150 | 42 | 224 | 662 | 497 | 450 |

  params, the same for every model here: `COLUMN_buckets_counted=['artifact', 'text']`, `COLUMN_full_width_box_share=0.6`, `COLUMN_min_boxes_per_page=2`, `COLUMN_x_overlap_of_narrow_box=0.5`, `order_rule_one_rule=ours_top_down_left_right (forced)`

  `PP-DocLayoutV2` differs: `order_rule=model_rank`

  `PP-DocLayoutV3` differs: `order_rule=model_rank`

  `PP-DocLayout_plus-L` differs: `order_rule=ours_top_down_left_right: the model gives no rank`

  `docling-egret` differs: `order_rule=ours_top_down_left_right`

  `docling-heron` differs: `order_rule=ours_top_down_left_right`

  `yolox_l0.05` differs: `order_rule=ours_top_down_left_right`

**contour**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `artefacts_called_text` ↓ | 0.000 <sub>0/3</sub> | 0.000 <sub>0/3</sub> | 0.000 <sub>0/3</sub> | 0.000 <sub>0/3</sub> | 0.000 <sub>0/3</sub> | 0.000 <sub>0/3</sub> |
| `artefacts_cropped` ↓ | 0.000 <sub>0/3</sub> | 0.000 <sub>0/3</sub> | 0.000 <sub>0/3</sub> | 0.000 <sub>0/3</sub> | 0.000 <sub>0/3</sub> | 0.000 <sub>0/3</sub> |
| `artefacts_found` ↑ | 0.667 <sub>2/3</sub> | 0.667 <sub>2/3</sub> | 1.000 <sub>3/3</sub> | 0.667 <sub>2/3</sub> | 0.667 <sub>2/3</sub> | 0.333 <sub>1/3</sub> |
| `artefacts_merged` = | 0.000 <sub>0/3</sub> | 0.000 <sub>0/3</sub> | 0.000 <sub>0/3</sub> | 0.000 <sub>0/3</sub> | 0.000 <sub>0/3</sub> | 0.000 <sub>0/3</sub> |
| `artefacts_not_seen` ↓ | 0.333 <sub>1/3</sub> | 0.333 <sub>1/3</sub> | 0.000 <sub>0/3</sub> | 0.333 <sub>1/3</sub> | 0.333 <sub>1/3</sub> | 0.667 <sub>2/3</sub> |
| `assembly_order` ↑ | 0.886 | 0.999 | 0.730 | 0.683 | 0.689 | 0.686 |
| `label_errors` ↓ | 207 <sub>207/517</sub> | 442 <sub>442/495</sub> | 233 <sub>233/239</sub> | — | — | — |
| `model_order` ↑ | 0.886 | 0.999 | — | — | — | — |
| `role_errors` ↓ | 1 <sub>1/517</sub> | 0 <sub>0/495</sub> | 0 <sub>0/239</sub> | 1 <sub>1/496</sub> | 3 <sub>3/519</sub> | 0 <sub>0/485</sub> |
| `sense_whole` ↑ | 0.667 <sub>2/3</sub> | 0.667 <sub>2/3</sub> | 1.000 <sub>3/3</sub> | 0.667 <sub>2/3</sub> | 0.667 <sub>2/3</sub> | 0.333 <sub>1/3</sub> |
| `text_furniture_found` ↑ | 0.990 <sub>515/520</sub> | 0.948 <sub>493/520</sub> | 0.454 <sub>236/520</sub> | 0.950 <sub>494/520</sub> | 0.994 <sub>517/520</sub> | 0.931 <sub>484/520</sub> |

- a dash: the model gives no rank (ours_top_down_left_right)
- a dash: the model gives no rank (ours_top_down_left_right: the model gives no rank)
- a dash: the two sides speak different label vocabularies; not compared

  params, the same for every model here: `COLUMN_buckets_counted=['artifact', 'text']`, `COLUMN_full_width_box_share=0.6`, `COLUMN_min_boxes_per_page=2`, `COLUMN_x_overlap_of_narrow_box=0.5`, `COVER_MATCH=0.75`, `SENSE_NEIGHBOUR=0.5`, `SENSE_WHOLE=0.9`, `TOL_PX=6.0`, `TOUCH=0.1`

**fitness**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `area_under_boxes` = | 0.665 <sub>6792980/10219040</sub> | 0.703 <sub>7180445/10219040</sub> | 0.665 <sub>6794527/10219040</sub> | 0.585 <sub>5981796/10219040</sub> | 0.582 <sub>5945155/10219040</sub> | 0.498 <sub>5086134/10219040</sub> |
| `boxes_per_page` = | 43.692 <sub>568/13</sub> | 40.846 <sub>531/13</sub> | 20.231 <sub>263/13</sub> | 62.692 <sub>815/13</sub> | 61.769 <sub>803/13</sub> | 40.000 <sub>520/13</sub> |
| `ink_as_picture` = | — | — | — | — | — | — |
| `ink_as_text` ↑ | — | — | — | — | — | — |
| `ink_junk` = | 0.000 <sub>0/1057663</sub> | 0.000 <sub>0/1057663</sub> | 0.000 <sub>0/1057663</sub> | 0.000 <sub>0/1057663</sub> | 0.000 <sub>0/1057663</sub> | 0.000 <sub>0/1057663</sub> |
| `ink_under_artefacts` = | 0.031 <sub>33235/1057663</sub> | 0.127 <sub>134245/1057663</sub> | 0.286 <sub>302705/1057663</sub> | 0.086 <sub>90884/1057663</sub> | 0.005 <sub>5681/1057663</sub> | 0.003 <sub>3662/1057663</sub> |
| `ink_under_boxes` ↑ | 0.976 <sub>1032695/1057663</sub> | 0.986 <sub>1043227/1057663</sub> | 0.868 <sub>918559/1057663</sub> | 0.980 <sub>1036339/1057663</sub> | 0.982 <sub>1038992/1057663</sub> | 0.897 <sub>949009/1057663</sub> |
| `ink_under_boxes_clean` ↑ | 0.976 <sub>1032695/1057663</sub> | 0.986 <sub>1043227/1057663</sub> | 0.868 <sub>918559/1057663</sub> | 0.980 <sub>1036339/1057663</sub> | 0.982 <sub>1038992/1057663</sub> | 0.897 <sub>949009/1057663</sub> |
| `median_box_area` = | 0.016 | 0.015 | 0.015 | 0.012 | 0.014 | 0.013 |
| `object_ink_preserved` ↑ | 0.928 <sub>33218/35792</sub> | 0.933 <sub>33409/35792</sub> | 0.979 <sub>35041/35792</sub> | 0.150 <sub>5381/35792</sub> | 0.159 <sub>5681/35792</sub> | 0.102 <sub>3662/35792</sub> |
| `objects_in_one_box` ↑ | 0.333 <sub>1/3</sub> | 0.333 <sub>1/3</sub> | 0.667 <sub>2/3</sub> | 0.333 <sub>1/3</sub> | 0.667 <sub>2/3</sub> | 0.000 <sub>0/3</sub> |
| `objects_intact` ↑ | 0.333 <sub>1/3</sub> | 0.333 <sub>1/3</sub> | 0.667 <sub>2/3</sub> | 0.333 <sub>1/3</sub> | 0.667 <sub>2/3</sub> | 0.000 <sub>0/3</sub> |
| `objects_left_as_text` ↓ | 0.333 <sub>1/3</sub> | 0.000 <sub>0/3</sub> | 0.000 <sub>0/3</sub> | 0.000 <sub>0/3</sub> | 0.333 <sub>1/3</sub> | 0.000 <sub>0/3</sub> |
| `objects_torn` ↓ | 0.333 <sub>1/3</sub> | 0.333 <sub>1/3</sub> | 0.000 <sub>0/3</sub> | 0.333 <sub>1/3</sub> | 0.333 <sub>1/3</sub> | 0.667 <sub>2/3</sub> |
| `objects_with_company` ↓ | 0.000 <sub>0/3</sub> | 0.000 <sub>0/3</sub> | 0.000 <sub>0/3</sub> | 0.000 <sub>0/3</sub> | 0.000 <sub>0/3</sub> | 0.000 <sub>0/3</sub> |

- a dash: this run read nothing: every block would leave as a picture, which is not a measurement of one

  params, the same for every model here: `GUTTER=0.5`, `GUTTER_BAND=0.2`, `JUNK_WIDTH=0.1`, `MID=0.2`, `MIN_SPREAD_RATIO=1.15`, `RULE_RUN=0.25`, `almost=0.95`, `bitten=0.8`, `dpi=[144]`, `edge_band=0.04`, `ink=160`, `intact=0.99`

**snapshot**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `empty` ↓ | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 17 <sub>17/79</sub> |
| `fingerprint_verified` = | 0 | 0 | 0 | 0 | 0 | 1 |
| `missing` ↓ | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/79</sub> |
| `values_present` = | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 79 <sub>79/79</sub> |

### spravochnik

**assembly**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `excess_jumps` ↓ | 2 | 16 | 131 | 204 | 132 | 126 |
| `excess_jumps_per_page` ↓ | 0.111 <sub>over 18/36 pages</sub> | 1.455 <sub>over 11/36 pages</sub> | 7.278 <sub>over 18/36 pages</sub> | 10.737 <sub>over 19/36 pages</sub> | 6.600 <sub>over 20/36 pages</sub> | 11.455 <sub>over 11/36 pages</sub> |
| `excess_jumps_per_transition` ↓ | 0.091 <sub>2/22</sub> | 0.640 <sub>16/25</sub> | 0.897 <sub>131/146</sub> | 0.891 <sub>204/229</sub> | 0.841 <sub>132/157</sub> | 0.920 <sub>126/137</sub> |
| `excess_jumps_per_transition_one_rule` ↓ | 0.868 <sub>131/151</sub> | 0.893 <sub>75/84</sub> | 0.897 <sub>131/146</sub> | 0.891 <sub>204/229</sub> | 0.841 <sub>132/157</sub> | 0.920 <sub>126/137</sub> |
| `pages_with_columns` = | 16 <sub>16/36</sub> | 9 <sub>9/36</sub> | 12 <sub>12/36</sub> | 16 <sub>16/36</sub> | 17 <sub>17/36</sub> | 9 <sub>9/36</sub> |
| `transitions` = | 22 | 25 | 146 | 229 | 157 | 137 |

  params, the same for every model here: `COLUMN_buckets_counted=['artifact', 'text']`, `COLUMN_full_width_box_share=0.6`, `COLUMN_min_boxes_per_page=2`, `COLUMN_x_overlap_of_narrow_box=0.5`, `order_rule_one_rule=ours_top_down_left_right (forced)`

  `PP-DocLayoutV2` differs: `order_rule=model_rank`

  `PP-DocLayoutV3` differs: `order_rule=model_rank`

  `PP-DocLayout_plus-L` differs: `order_rule=ours_top_down_left_right: the model gives no rank`

  `docling-egret` differs: `order_rule=ours_top_down_left_right`

  `docling-heron` differs: `order_rule=ours_top_down_left_right`

  `yolox_l0.05` differs: `order_rule=ours_top_down_left_right`

**contour**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `artefacts_called_text` ↓ | 0.000 <sub>0/45</sub> | 0.000 <sub>0/45</sub> | 0.000 <sub>0/45</sub> | 0.044 <sub>2/45</sub> | 0.044 <sub>2/45</sub> | 0.000 <sub>0/45</sub> |
| `artefacts_cropped` ↓ | 0.022 <sub>1/45</sub> | 0.000 <sub>0/45</sub> | 0.022 <sub>1/45</sub> | 0.022 <sub>1/45</sub> | 0.022 <sub>1/45</sub> | 0.044 <sub>2/45</sub> |
| `artefacts_found` ↑ | 0.756 <sub>34/45</sub> | 0.689 <sub>31/45</sub> | 0.733 <sub>33/45</sub> | 0.733 <sub>33/45</sub> | 0.800 <sub>36/45</sub> | 0.267 <sub>12/45</sub> |
| `artefacts_merged` = | 0.156 <sub>7/45</sub> | 0.244 <sub>11/45</sub> | 0.178 <sub>8/45</sub> | 0.156 <sub>7/45</sub> | 0.133 <sub>6/45</sub> | 0.244 <sub>11/45</sub> |
| `artefacts_not_seen` ↓ | 0.044 <sub>2/45</sub> | 0.067 <sub>3/45</sub> | 0.044 <sub>2/45</sub> | 0.067 <sub>3/45</sub> | 0.022 <sub>1/45</sub> | 0.289 <sub>13/45</sub> |
| `assembly_order` ↑ | 0.989 | 0.985 | 0.807 | 0.803 | 0.809 | 0.798 |
| `label_errors` ↓ | 15 <sub>15/356</sub> | 8 <sub>8/287</sub> | — | — | — | — |
| `model_order` ↑ | 0.989 | 0.985 | — | — | — | — |
| `role_errors` ↓ | 3 <sub>3/356</sub> | 4 <sub>4/287</sub> | 3 <sub>3/362</sub> | 6 <sub>6/357</sub> | 2 <sub>2/372</sub> | 4 <sub>4/326</sub> |
| `sense_whole` ↑ | 0.778 <sub>35/45</sub> | 0.689 <sub>31/45</sub> | 0.756 <sub>34/45</sub> | 0.711 <sub>32/45</sub> | 0.778 <sub>35/45</sub> | 0.422 <sub>19/45</sub> |
| `text_furniture_found` ↑ | 0.955 <sub>322/337</sub> | 0.760 <sub>256/337</sub> | 0.976 <sub>329/337</sub> | 0.955 <sub>322/337</sub> | 0.991 <sub>334/337</sub> | 0.932 <sub>314/337</sub> |

- a dash: the model gives no rank (ours_top_down_left_right)
- a dash: the model gives no rank (ours_top_down_left_right: the model gives no rank)
- a dash: the two sides speak different label vocabularies; not compared

  params, the same for every model here: `COLUMN_buckets_counted=['artifact', 'text']`, `COLUMN_full_width_box_share=0.6`, `COLUMN_min_boxes_per_page=2`, `COLUMN_x_overlap_of_narrow_box=0.5`, `COVER_MATCH=0.75`, `SENSE_NEIGHBOUR=0.5`, `SENSE_WHOLE=0.9`, `TOL_PX=6.0`, `TOUCH=0.1`

**fitness**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `area_under_boxes` = | 0.564 <sub>33486545/59343680</sub> | 0.590 <sub>35021725/59343680</sub> | 0.573 <sub>34008658/59343680</sub> | 0.557 <sub>33039461/59343680</sub> | 0.554 <sub>32882942/59343680</sub> | 0.520 <sub>30876394/59343680</sub> |
| `boxes_per_page` = | 10.194 <sub>367/36</sub> | 8.278 <sub>298/36</sub> | 10.472 <sub>377/36</sub> | 17.111 <sub>616/36</sub> | 11.444 <sub>412/36</sub> | 9.722 <sub>350/36</sub> |
| `ink_as_picture` = | — | — | — | — | — | — |
| `ink_as_text` ↑ | — | — | — | — | — | — |
| `ink_junk` = | 0.016 <sub>115675/7443469</sub> | 0.016 <sub>115675/7443469</sub> | 0.016 <sub>115675/7443469</sub> | 0.016 <sub>115675/7443469</sub> | 0.016 <sub>115675/7443469</sub> | 0.016 <sub>115675/7443469</sub> |
| `ink_under_artefacts` = | 0.172 <sub>1277700/7443469</sub> | 0.276 <sub>2056386/7443469</sub> | 0.176 <sub>1308829/7443469</sub> | 0.124 <sub>921565/7443469</sub> | 0.142 <sub>1056158/7443469</sub> | 0.141 <sub>1048564/7443469</sub> |
| `ink_under_boxes` ↑ | 0.963 <sub>7170933/7443469</sub> | 0.953 <sub>7090749/7443469</sub> | 0.969 <sub>7211591/7443469</sub> | 0.967 <sub>7197149/7443469</sub> | 0.973 <sub>7244408/7443469</sub> | 0.906 <sub>6743174/7443469</sub> |
| `ink_under_boxes_clean` ↑ | 0.979 <sub>7170933/7327794</sub> | 0.958 <sub>7017726/7327794</sub> | 0.984 <sub>7211591/7327794</sub> | 0.982 <sub>7197149/7327794</sub> | 0.986 <sub>7227284/7327794</sub> | 0.920 <sub>6743174/7327794</sub> |
| `median_box_area` = | 0.041 | 0.047 | 0.037 | 0.021 | 0.036 | 0.034 |
| `object_ink_preserved` ↑ | 0.925 <sub>1159274/1253127</sub> | 0.945 <sub>1184191/1253127</sub> | 0.945 <sub>1184531/1253127</sub> | 0.728 <sub>912197/1253127</sub> | 0.843 <sub>1056143/1253127</sub> | 0.707 <sub>886497/1253127</sub> |
| `objects_in_one_box` ↑ | 0.711 <sub>32/45</sub> | 0.778 <sub>35/45</sub> | 0.689 <sub>31/45</sub> | 0.756 <sub>34/45</sub> | 0.778 <sub>35/45</sub> | 0.400 <sub>18/45</sub> |
| `objects_intact` ↑ | 0.711 <sub>32/45</sub> | 0.800 <sub>36/45</sub> | 0.689 <sub>31/45</sub> | 0.756 <sub>34/45</sub> | 0.778 <sub>35/45</sub> | 0.400 <sub>18/45</sub> |
| `objects_left_as_text` ↓ | 0.022 <sub>1/45</sub> | 0.000 <sub>0/45</sub> | 0.022 <sub>1/45</sub> | 0.133 <sub>6/45</sub> | 0.089 <sub>4/45</sub> | 0.000 <sub>0/45</sub> |
| `objects_torn` ↓ | 0.111 <sub>5/45</sub> | 0.044 <sub>2/45</sub> | 0.133 <sub>6/45</sub> | 0.133 <sub>6/45</sub> | 0.089 <sub>4/45</sub> | 0.378 <sub>17/45</sub> |
| `objects_with_company` ↓ | 0.156 <sub>7/45</sub> | 0.200 <sub>9/45</sub> | 0.156 <sub>7/45</sub> | 0.200 <sub>9/45</sub> | 0.156 <sub>7/45</sub> | 0.244 <sub>11/45</sub> |

- a dash: this run read nothing: every block would leave as a picture, which is not a measurement of one

  params, the same for every model here: `GUTTER=0.5`, `GUTTER_BAND=0.2`, `JUNK_WIDTH=0.1`, `MID=0.2`, `MIN_SPREAD_RATIO=1.15`, `RULE_RUN=0.25`, `almost=0.95`, `bitten=0.8`, `dpi=[144]`, `edge_band=0.04`, `ink=160`, `intact=0.99`

**snapshot**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `empty` ↓ | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 17 <sub>17/79</sub> |
| `fingerprint_verified` = | 0 | 0 | 0 | 0 | 0 | 1 |
| `missing` ↓ | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/79</sub> |
| `values_present` = | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 79 <sub>79/79</sub> |

### zhurnal

**assembly**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `excess_jumps` ↓ | 0 | 20 | 124 | 129 | 140 | 122 |
| `excess_jumps_per_page` ↓ | 0.000 | 2.500 <sub>over 8/10 pages</sub> | 12.400 | 12.900 | 14.000 | 13.556 <sub>over 9/10 pages</sub> |
| `excess_jumps_per_transition` ↓ | 0.000 <sub>0/10</sub> | 0.714 <sub>20/28</sub> | 0.925 <sub>124/134</sub> | 0.928 <sub>129/139</sub> | 0.933 <sub>140/150</sub> | 0.931 <sub>122/131</sub> |
| `excess_jumps_per_transition_one_rule` ↓ | 0.925 <sub>123/133</sub> | 0.930 <sub>106/114</sub> | 0.925 <sub>124/134</sub> | 0.928 <sub>129/139</sub> | 0.933 <sub>140/150</sub> | 0.931 <sub>122/131</sub> |
| `pages_with_columns` = | 10 <sub>10/10</sub> | 8 <sub>8/10</sub> | 10 <sub>10/10</sub> | 10 <sub>10/10</sub> | 10 <sub>10/10</sub> | 9 <sub>9/10</sub> |
| `transitions` = | 10 | 28 | 134 | 139 | 150 | 131 |

  params, the same for every model here: `COLUMN_buckets_counted=['artifact', 'text']`, `COLUMN_full_width_box_share=0.6`, `COLUMN_min_boxes_per_page=2`, `COLUMN_x_overlap_of_narrow_box=0.5`, `order_rule_one_rule=ours_top_down_left_right (forced)`

  `PP-DocLayoutV2` differs: `order_rule=model_rank`

  `PP-DocLayoutV3` differs: `order_rule=model_rank`

  `PP-DocLayout_plus-L` differs: `order_rule=ours_top_down_left_right: the model gives no rank`

  `docling-egret` differs: `order_rule=ours_top_down_left_right`

  `docling-heron` differs: `order_rule=ours_top_down_left_right`

  `yolox_l0.05` differs: `order_rule=ours_top_down_left_right`

**contour**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `artefacts_called_text` ↓ | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> |
| `artefacts_cropped` ↓ | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> |
| `artefacts_found` ↑ | 0.833 <sub>5/6</sub> | 1.000 <sub>6/6</sub> | 1.000 <sub>6/6</sub> | 1.000 <sub>6/6</sub> | 1.000 <sub>6/6</sub> | 0.667 <sub>4/6</sub> |
| `artefacts_merged` = | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> |
| `artefacts_not_seen` ↓ | 0.167 <sub>1/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.167 <sub>1/6</sub> |
| `assembly_order` ↑ | 1.000 | 0.970 | 0.773 | 0.769 | 0.771 | 0.749 |
| `label_errors` ↓ | 7 <sub>7/180</sub> | 2 <sub>2/166</sub> | 6 <sub>6/181</sub> | — | — | — |
| `model_order` ↑ | 1.000 | 0.970 | — | — | — | — |
| `role_errors` ↓ | 1 <sub>1/180</sub> | 0 <sub>0/166</sub> | 0 <sub>0/181</sub> | 4 <sub>4/186</sub> | 1 <sub>1/187</sub> | 1 <sub>1/164</sub> |
| `sense_whole` ↑ | 0.833 <sub>5/6</sub> | 1.000 <sub>6/6</sub> | 1.000 <sub>6/6</sub> | 1.000 <sub>6/6</sub> | 1.000 <sub>6/6</sub> | 0.833 <sub>5/6</sub> |
| `text_furniture_found` ↑ | 0.956 <sub>175/183</sub> | 0.874 <sub>160/183</sub> | 0.956 <sub>175/183</sub> | 0.984 <sub>180/183</sub> | 0.989 <sub>181/183</sub> | 0.874 <sub>160/183</sub> |

- a dash: the model gives no rank (ours_top_down_left_right)
- a dash: the model gives no rank (ours_top_down_left_right: the model gives no rank)
- a dash: the two sides speak different label vocabularies; not compared

  params, the same for every model here: `COLUMN_buckets_counted=['artifact', 'text']`, `COLUMN_full_width_box_share=0.6`, `COLUMN_min_boxes_per_page=2`, `COLUMN_x_overlap_of_narrow_box=0.5`, `COVER_MATCH=0.75`, `SENSE_NEIGHBOUR=0.5`, `SENSE_WHOLE=0.9`, `TOL_PX=6.0`, `TOUCH=0.1`

**fitness**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `area_under_boxes` = | 0.565 <sub>9272904/16416000</sub> | 0.548 <sub>8993137/16416000</sub> | 0.535 <sub>8781798/16416000</sub> | 0.547 <sub>8985911/16416000</sub> | 0.542 <sub>8905157/16416000</sub> | 0.455 <sub>7465355/16416000</sub> |
| `boxes_per_page` = | 18.900 <sub>189/10</sub> | 17.100 <sub>171/10</sub> | 18.800 <sub>188/10</sub> | 26.200 <sub>262/10</sub> | 25.500 <sub>255/10</sub> | 17.200 <sub>172/10</sub> |
| `ink_as_picture` = | — | — | — | — | — | — |
| `ink_as_text` ↑ | — | — | — | — | — | — |
| `ink_junk` = | 0.000 <sub>0/2367945</sub> | 0.000 <sub>0/2367945</sub> | 0.000 <sub>0/2367945</sub> | 0.000 <sub>0/2367945</sub> | 0.000 <sub>0/2367945</sub> | 0.000 <sub>0/2367945</sub> |
| `ink_under_artefacts` = | 0.063 <sub>149612/2367945</sub> | 0.180 <sub>426140/2367945</sub> | 0.068 <sub>161072/2367945</sub> | 0.069 <sub>163778/2367945</sub> | 0.069 <sub>163368/2367945</sub> | 0.062 <sub>147609/2367945</sub> |
| `ink_under_boxes` ↑ | 0.990 <sub>2343459/2367945</sub> | 0.900 <sub>2131854/2367945</sub> | 0.988 <sub>2340141/2367945</sub> | 0.990 <sub>2345179/2367945</sub> | 0.990 <sub>2344706/2367945</sub> | 0.890 <sub>2107054/2367945</sub> |
| `ink_under_boxes_clean` ↑ | 0.990 <sub>2343459/2367945</sub> | 0.900 <sub>2131854/2367945</sub> | 0.988 <sub>2340141/2367945</sub> | 0.990 <sub>2345179/2367945</sub> | 0.990 <sub>2344706/2367945</sub> | 0.890 <sub>2107054/2367945</sub> |
| `median_box_area` = | 0.026 | 0.026 | 0.024 | 0.020 | 0.020 | 0.023 |
| `object_ink_preserved` ↑ | 0.913 <sub>149586/163915</sub> | 0.987 <sub>161766/163915</sub> | 0.983 <sub>161057/163915</sub> | 0.999 <sub>163764/163915</sub> | 0.997 <sub>163364/163915</sub> | 0.898 <sub>147146/163915</sub> |
| `objects_in_one_box` ↑ | 0.500 <sub>3/6</sub> | 0.667 <sub>4/6</sub> | 0.667 <sub>4/6</sub> | 0.833 <sub>5/6</sub> | 0.667 <sub>4/6</sub> | 0.333 <sub>2/6</sub> |
| `objects_intact` ↑ | 0.500 <sub>3/6</sub> | 0.667 <sub>4/6</sub> | 0.667 <sub>4/6</sub> | 0.833 <sub>5/6</sub> | 0.667 <sub>4/6</sub> | 0.333 <sub>2/6</sub> |
| `objects_left_as_text` ↓ | 0.167 <sub>1/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> |
| `objects_torn` ↓ | 0.167 <sub>1/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.333 <sub>2/6</sub> |
| `objects_with_company` ↓ | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> | 0.000 <sub>0/6</sub> |

- a dash: this run read nothing: every block would leave as a picture, which is not a measurement of one

  params, the same for every model here: `GUTTER=0.5`, `GUTTER_BAND=0.2`, `JUNK_WIDTH=0.1`, `MID=0.2`, `MIN_SPREAD_RATIO=1.15`, `RULE_RUN=0.25`, `almost=0.95`, `bitten=0.8`, `dpi=[144]`, `edge_band=0.04`, `ink=160`, `intact=0.99`

**snapshot**

| scalar | PP-DocLayoutV2 | PP-DocLayoutV3 | PP-DocLayout_plus-L | docling-egret | docling-heron | yolox_l0.05 |
|---|---|---|---|---|---|---|
| `empty` ↓ | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 13 <sub>13/52</sub> | 17 <sub>17/79</sub> |
| `fingerprint_verified` = | 0 | 0 | 0 | 0 | 0 | 1 |
| `missing` ↓ | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/52</sub> | 0 <sub>0/79</sub> |
| `values_present` = | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 52 <sub>52/52</sub> | 79 <sub>79/79</sub> |

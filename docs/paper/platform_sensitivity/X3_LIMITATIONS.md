# X3 limitations

1. **Synthesis only.** X3 collected no data and changed no metric definition.
   Every count was recomputed from the frozen X1 evidence; where a recomputed
   value had been anticipated, the frozen evidence — not the expectation — is
   the source.
2. **The TA axis is never isolated.** In CLASS B the subsystem, Fast Models
   implementation and TA state change together; `NOT_SEPARATED` stands. CLASS A
   holds TA constant only at `TA_OFF`.
3. **The CLASS A result is narrow.** One NPU (U65), one platform pair, 14
   cells, one TA condition. It is classified
   `NO_OBSERVED_CYCLE_DIFFERENCE_UNDER_TESTED_TA_OFF_PAIR` and is not
   generalized; transfer to TA-ON is `NOT_EVALUABLE`.
4. **Threshold fragility is a property of the class definition.** The eight
   disagreements are crossings of the frozen 0.75 cut point, not reversals of
   scaling direction. The threshold is not retuned here.
5. **Normalized cost is compared as an ordering only.** No L1/L2/RMSE or
   value-correlation similarity between normalized vectors is computed; none
   was ever preregistered.
6. **U85 has no peer platform**, so no U85 cell entered X1 or X3; its
   connection to the other generations remains dimensionless/structural, as in
   the frozen manuscript.
7. **`wav2letter` has no U55 ladder** (executable only at MAC 256 on both U55
   platforms), so it contributes to ranking there and is absent from U55
   scaling, class and saturation universes.

*Part of the FIREWATCH spec, see [`../CLAUDE.md`](../CLAUDE.md) and [`../context.md`](../context.md).*

# FIREWATCH, References

Keys match the short cites used in `LITERATURE_REVIEW.md`. Confirm exact page/DOI at write-up time; do not add a reference you have not personally opened.

### Segmentation / detection
- **[Ravi2024/SAM2]** N. Ravi et al. "SAM 2: Segment Anything in Images and Videos." Meta AI, 2024. (Promptable video segmentation with streaming memory; SA-V dataset.)
- **[Dewangan2022]** A. Dewangan et al. "FIgLib & SmokeyNet: Dataset and Deep Learning Model for Real-Time Wildland Fire Smoke Detection." *Remote Sensing* 14(4):1007, 2022.
- **[Shamsoshoara2021]** A. Shamsoshoara et al. "Aerial imagery pile burn detection using deep learning: The FLAME dataset." *Computer Networks*, 2021. (FLAME; see also FLAME2.)
- **[Gaur2024/Review]** Fire-and-smoke-from-video literature review under a novel taxonomy (~150 papers, ~17 datasets). *Expert Systems with Applications*, 2024.
- AusSmoke / MultiNatSmoke smoke-segmentation datasets (arXiv, 2024-2026).

### Satellite active fire
- **[Giglio]** L. Giglio et al. MODIS fire products (MOD14). *Remote Sensing of Environment*, 2003/2016.
- **[Schroeder]** W. Schroeder et al. VIIRS 375 m active fire product.
- NASA FIRMS (Fire Information for Resource Management System), NRT distribution + API.
- NOAA/NESDIS GOES-R ABI Fire Detection & Characterization (FDC) product (geostationary, ~5-min CONUS).

### Fire-spread modeling (physics)
- **[Rothermel1972]** R.C. Rothermel. "A mathematical model for predicting fire spread in wildland fuels." USDA Forest Service Research Paper INT-115, 1972.
- FARSITE / FlamMap, M.A. Finney, USDA FS.
- ELMFIRE, C. Lautenberger. "Wildland fire modeling with an Eulerian level set method..." 2013.
- **[Coen2013]** J. Coen et al. "WRF-Fire: Coupled Weather-Wildland Fire Modeling with WRF." *J. Appl. Meteorol. Climatol.* 52:16-38, 2013.
- **[Mandel2011/WRF-SFIRE]** J. Mandel, J.D. Beezley, A.K. Kochanski. "Coupled atmosphere-wildland fire modeling with WRF 3.3 and SFIRE 2011." *Geoscientific Model Development* 4:591-610, 2011.

### Data-driven spread datasets / forecasting
- **[Huot2022]** F. Huot et al. "Next Day Wildfire Spread: A Machine Learning Dataset to Predict Wildfire Spreading From Remote-Sensing Data." *IEEE TGRS* 60:1-13, 2022.
- **[Gerard2023]** S. Gerard, Y. Zhao, J. Sullivan. "WildfireSpreadTS: A dataset of multi-modal time series for wildfire spread prediction." *NeurIPS 2023* Datasets & Benchmarks. (13,607 images, 607 US fire events, 2018-2021, 23 channels; Zenodo 10.5281/zenodo.8006177.)
- **[Lahrichi2025]** S. Lahrichi et al. "Advancing Time Series Wildfire Spread Prediction: Modeling Improvements and the WSTS+ Benchmark." arXiv:2502.12003, 2025.
- **[Kondylatos2023]** S. Kondylatos et al. "Mesogeos: A Multi-purpose Dataset for Data-driven Wildfire Modeling in the Mediterranean." *NeurIPS 2023* Datasets & Benchmarks.
- **[Karasante2025]** I. Karasante et al. "SeasFire Cube: A Multivariate Dataset for Global Wildfire Modeling." *Scientific Data* 12:368, 2025.
- **[Li2024]** "Sim2Real-Fire: A Multi-modal Simulation Dataset for Forecast and Backtracking of Real-world Forest Fire." *NeurIPS 2024* Datasets & Benchmarks.
- TS-SatFire (multi-task satellite time-series for fire detection+prediction), *Scientific Data*, 2025.

### Data assimilation for wildfire (the core lineage)
- **[Mandel2008]** J. Mandel, L.S. Bennethum, J.D. Beezley, J.L. Coen, C.C. Douglas, M. Kim, A. Vodacek. "A wildland fire model with data assimilation." *Mathematics and Computers in Simulation* 79:584-606, 2008.
- **[Mandel2009]** J. Mandel, J.D. Beezley, J.L. Coen, M. Kim. "Data Assimilation for Wildland Fires: Ensemble Kalman filters in coupled atmosphere-surface models." *IEEE Control Systems Magazine* 29:47-65, 2009.
- **[Beezley2008]** J.D. Beezley, J. Mandel. "Morphing ensemble Kalman filters." *Tellus A* 60:131-140, 2008.
- **[Rochoux2014]** M.C. Rochoux, S. Ricci, D. Lucor, B. Cuenot, A. Trouvé. "Towards predictive data-driven simulations of wildfire spread - Part I: Reduced-cost ensemble Kalman filter based on a polynomial chaos surrogate." *Natural Hazards and Earth System Sciences*, 2014. (Part II 2015.)
- **[Mandel2016]** J. Mandel, A. Fournier, M.A. Jenkins, A.K. Kochanski, S. Schranz, M. Vejmelka. "Assimilation of Satellite Active Fires Detection Into a Coupled Weather-Fire Model." 5th Intl. Fire Behavior and Fuels Conf., 2016.
- FARSITE + EnKF perimeter/fuel assimilation, *Procedia Computer Science / ICCS*, 2016.

### Camera-to-map georeferencing
- **[Santana2022]** P. Santana et al. "Real-Time Georeferencing of Fire Front Aerial Images Using Iterative Ray-Tracing and the Bearings-Range Extended Kalman Filter." *Sensors*, 2022. (PMC8838670.)
- **[MPT2021]** "Georeferencing Oblique Aerial Wildfire Photographs: An Untapped Source of Fire Behaviour Data." *Fire* 4(4):81, 2021. (WSL Monoplotting Tool; sub-meter fronts; rate-of-spread.)
- **[rs17233911]** "DEM-Based UAV Geolocation of Thermal Hotspots on Complex Terrain." *Remote Sensing* 17(23):3911, 2025.
- Pyronear `smoke-localization` (open-source): pixel→terrain GPS projection for wildfire cameras.

### Calibration
- **[Guo2017]** C. Guo, G. Pleiss, Y. Sun, K.Q. Weinberger. "On Calibration of Modern Neural Networks." *ICML 2017*.

### Assets / access
- NOAA HRRR (AWS Open Data; `Herbie`). USGS 3DEP / SRTM DEM. LANDFIRE fuels/vegetation.
- NIFC / WFIGS operational perimeters. MTBS burn-severity perimeters.
- Microsoft Building Footprints; OpenStreetMap; US Census.
- ALERTCalifornia / ALERTWildfire camera network (HPWREN heritage).

### Operational context
- AEM Elements 360 / Multi-Source Ignition Detection (MSID), commercial camera+satellite+weather fusion (situational awareness / alerting), cited as evidence the integration thesis is valued.

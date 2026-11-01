# SCIN visual reference set

This folder contains a small set of original SCIN skin-condition images and a manifest mapping each sample to its published dermatologist-weighted differential label. The app may show a few label-matched samples to the local vision model for cautious visual comparison. The images are not a diagnostic test set, and their labels are not confirmed diagnoses.

Source: [SCIN dataset by Google Research](https://github.com/google-research-datasets/scin), collected from volunteer image donors who provided consent. The dataset contains dermatologist-provided differential labels and skin-tone information. This app retains only selected images and condition labels; it does not retain case IDs or donor demographics. Groin/genital samples are excluded.

The SCIN Data Use License is included as `SCIN_LICENSE.txt`. When redistributing these images, include that license and this attribution. Dataset paper: Ward et al., “Creating an Empirical Dermatology Dataset Through Crowdsourcing With Web Search Advertisements,” *JAMA Network Open* (2024), [doi:10.1001/jamanetworkopen.2024.46615](https://doi.org/10.1001/jamanetworkopen.2024.46615).

SCIN references are provided for health education and research. A visual resemblance can be misleading and must not be treated as a diagnosis. The user image and selected references are sent only to the configured Ollama server for local inference; the app does not save user photos.

To rebuild or refresh the image subset while online, run `python tools/build_skin_reference_set.py` from the project root. The app works offline after these files have been downloaded.

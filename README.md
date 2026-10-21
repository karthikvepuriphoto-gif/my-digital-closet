# My Digital Closet

A small wardrobe tracker. Add pieces, filter the closet, save outfits, and import clothes from pictures that already live on your computer.

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
streamlit run app.py
```

PyTorch is installed first, from the CPU index, so pip does not pull a multi-gigabyte CUDA build. The closet itself runs without PyTorch. Photo import is the part that needs it.

Closet data stays in `wardrobe_db.csv` and `outfits_db.csv` next to the app. Photos you add by hand are copied into `closet_images/`. Those files are not part of the git history.

## Import a wardrobe from photos

Open **Import**, enter a folder of pictures, and choose a crops folder that is **outside** that photo folder. The first time, choose **Download models**. That saves two open-source models into `model_cache/` next to the app:

- [SegFormer B2 clothes](https://huggingface.co/mattmdjaga/segformer_b2_clothes) finds people and clothing and cuts each garment out. It is about 110 MB and runs on CPU (a couple of seconds per photo on a laptop).
- MobileNetV3-Small (ImageNet weights, stored locally) turns each crop into a small numeric signature so the same piece in another photo can be recognized.

After that download, scans run on this machine. The app sets the Hugging Face and Transformers offline flags before loading the models, turns off their telemetry, and does not send a token.

**Scan next 8** is the comfortable way through a large folder. **Scan all remaining** keeps going. Progress is shown while it works. Each finished photo is recorded in `imported_wardrobe/library.json` by file size and modification time, so stopping and coming back skips photos that have not changed. A photo that was edited is scanned again. A photo the app cannot read is skipped and the rest of the folder continues.

Nothing is added to the closet until you approve it. On each suggestion you can change the name, category, color, and season, then approve or reject. **Approve all as suggested** accepts the current suggestions. Rejecting deletes that crop and remembers the signature, so the same piece is not suggested again. Approving moves the crop from `pending/` into a category folder and adds a closet row that links back to the original picture.

Suggested categories are tops, bottoms, dresses, outerwear, shoes, and accessories. A dress is stored as **Full Body** in the closet (so outfits can treat it as a one-piece) and the crop file goes in `dresses/`. SegFormer does not have a coat class. A long top is suggested as outerwear, and the review step is where you correct that.

The same piece in several photos is kept once when the signatures are very close and the category matches. A top and a coat suggestion can also collapse into one piece when the match is even closer, which is how a jacket labeled both ways stays a single item. Different angles sometimes stay as two suggestions; reject the extra one.

You can run the same steps without the app:

```bash
python photo_import.py download-models
python photo_import.py scan --source ~/Pictures/trip --output imported_wardrobe --limit 8
```

## Privacy

Your pictures stay on this computer. The scan only reads them. It does not upload them, does not send them to a cloud vision API, and does not edit, rename, or move them. If a photo changes while it is being read, the scan stops rather than writing a crop from a file that moved under it.

The model files are downloaded once, into `model_cache/`. Later scans are forced offline. Telemetry from the model tools is turned off, and the app does not attach a Hugging Face token. Crops are written only inside the crops folder you chose, which has to be outside the photo folder. A bug cannot delete or move an original to “clean up” a rejected guess: deletes are limited to files inside the crops folder.

Approving a piece adds it to your closet and stores the original photo’s path on that row, so you can see where it came from. Removing the closet row does not delete the original photo, and it does not delete the crop in the archive. The hand-added photos in `closet_images/` are the only image files the closet removes.

`model_cache/` and `imported_wardrobe/` stay on this machine and are gitignored.

## What the closet already does

- Browse, search, and filter by category, color, and season. All-season pieces stay visible when you filter to a season.
- Add a piece with a name. A photo is optional and is resized locally.
- Edit or remove a piece. Saved outfits that used it drop that slot.
- Build a look from separates or a one-piece, and save it.
- See a short read on what is taking up space. Charts start at zero.

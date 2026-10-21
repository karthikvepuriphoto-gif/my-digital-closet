# My Digital Closet

A private wardrobe you can open from a link on an iPhone or an Android phone, and also keep on your computer. Clothes and photos stay on the device. Nothing is uploaded to a closet server.

## Use it on a phone

Open the site in Chrome or Safari. The address is the link you publish with the steps below. That link is the app. The Play listing, further down, is separate and needs the site to be on HTTPS first.

- **Android:** the browser offers **Install**, or you can use the menu and choose **Add to Home screen** or **Install app**. That uses the site as an app. No Play Store is required for this step.
- **iPhone:** tap **Share**, then **Add to Home Screen**. iOS does not show the Android install button. The home-screen icon opens the same app.

The app works offline after the first visit. The closet itself is stored in the browser on that phone (IndexedDB). Deleting the home-screen icon does not always delete the data; clearing the site data for that address does.

### Import clothes from photos

Open **Import**. Choose photos, a folder (Chrome on Android and on a computer), or take a picture. The first scan downloads two open models into the browser, about 20 MB in total:

- [SegFormer B0 clothes](https://huggingface.co/Xenova/segformer_b0_clothes) (quantized, about 4 MB) finds a person and cuts out each garment. It is the small, phone-sized version of the same kind of model the computer app uses.
- [DINOv2 small](https://huggingface.co/Xenova/dinov2-small) (4-bit, about 15 MB) turns each crop into a signature so the same piece in another photo can be recognized. If that small file cannot load, the app tries the next size (about 24 MB).

That download is the model files only. The photos are not part of the request, and they are not sent to a vision API. Later scans use the cached models and run on the phone. **Scan next 4** is the comfortable batch. Stop whenever you want. Pick the same folder again later and photos that are unchanged (same name, size, and modified time) are skipped.

Nothing is added until you approve it. You can fix the name, category, color, and season first. A dress is stored as **Full Body** so a look can treat it as a one-piece, and its crop file goes in `dresses/`. The segmenter has no coat class, so a long top is only a suggestion of outerwear. Rejecting a guess drops the crop and remembers the signature. It does not delete the original photo, because the app never has permission to change files you did not pick as a save destination.

**Download crops (.zip)** saves approved photos in folders named `tops`, `bottoms`, `dresses`, `outerwear`, `shoes`, and `accessories`. In Chrome, **Save crops to a folder** writes those same folders into a directory you choose. Safari on iPhone can use the zip.

## Privacy

There is no account and no analytics. The publisher of the site cannot see the wardrobe.

Pieces, looks, and photos live in this browser’s private storage. The only network use is loading the app itself, and, the first time you scan, downloading the model files from their public host (Hugging Face, via the Transformers.js library on jsDelivr). Opening the closet does not download the models.

The plain-language policy that belongs on a Play listing is [`web/privacy.html`](web/privacy.html).

## Keep the computer app

The Python app is still here and still uses `wardrobe_db.csv`, `outfits_db.csv`, and `closet_images/`.

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
streamlit run app.py
```

PyTorch is installed first, from the CPU index, so pip does not pull a multi-gigabyte CUDA build. The closet itself runs without PyTorch. Photo import on the computer is optional and is described below.

```bash
python3 -m unittest test_wardrobe.py test_photo_import.py
node --test web/closet.test.js
```

### Computer photo import

On the computer, **Import** reads a folder path. Crops go to a separate folder, never inside the photo folder. The computer models are SegFormer B2 and MobileNetV3-Small, saved in `model_cache/`. See the notes that used to live here: originals are only read, telemetry from the model tools is turned off, and a scan can be resumed.

```bash
python photo_import.py download-models
python photo_import.py scan --source ~/Pictures/trip --output imported_wardrobe --limit 8
```

## Move a closet from the computer to the phone, or back

The files are the same shape in both places.

**Computer to phone.** In the phone app, open **Import** and find **Bring in a computer closet**. Choose `wardrobe_db.csv` and `outfits_db.csv` from the computer app’s folder. Optionally choose the pictures in `closet_images/` (or the whole folder). **Add to this closet** keeps what is already on the phone and updates rows that share an ID. **Replace this closet** swaps the phone’s pieces and looks for the file. A photo path of `None` still means “no photo,” same as the computer app.

**Phone to computer.** On the phone, choose **Download a closet backup**. Unzip it into the computer app’s folder so `wardrobe_db.csv`, `outfits_db.csv`, and `closet_images/` sit next to `app.py`. Then run `streamlit run app.py`.

A backup zip from the phone can also be chosen on another phone.

## Put the phone app on a free link

The site is the `web/` folder. It has no build step and no server. Any static host works. The host only sends the HTML, JavaScript, and icons. It never receives the photos.

### Cloudflare Pages

This is the better host if you also want Google Play, because Play has to read a file at `https://YOUR-HOST/.well-known/assetlinks.json`. That file is already in `web/.well-known/`.

1. Create a free [Cloudflare Pages](https://pages.cloudflare.com/) project.
2. Upload the contents of `web/` as the site root, or connect this GitHub repo and set the root directory to `web`.
3. The project gives you an address such as `https://my-digital-closet.pages.dev`. That address is the link you send people.

### GitHub Pages

1. Push this repo.
2. In the repo, open **Settings → Pages**.
3. Deploy from a branch. Use a branch whose root is the contents of `web/` (the `gh-pages` branch is the usual name), or set the site to serve the `web` folder if GitHub offers that.
4. The link looks like `https://YOUR-USER.github.io/my-digital-closet/`.

A project site on `github.io` cannot place `assetlinks.json` on the bare domain. That is fine for the installable link and for iPhone. For Play, use Cloudflare Pages, a custom domain, or a GitHub user site where this app is the whole site and `assetlinks.json` is at the host root.

## Google Play

The Play package is a [Trusted Web Activity](https://developer.chrome.com/docs/android/trusted-web-activity/) made with [Bubblewrap](https://github.com/GoogleChromeLabs/bubblewrap). It is a thin Android window around the same site, not a second copy of the closet and not a place where photos are processed. Capacitor would wrap the files inside an app binary. Bubblewrap fits better here because the link, the home-screen app, and the Play app are one site.

You need the site live on HTTPS first, with the manifest at `/manifest.webmanifest`.

1. Pay the one-time **$25** [Play Console registration fee](https://play.google.com/console/signup) and finish identity verification. Google sometimes holds new accounts for a few days.
2. Install the helper and Java (Bubblewrap asks for a JDK):

   ```bash
   npm install -g @bubblewrap/cli
   bubblewrap init --manifest=https://YOUR-HOST/manifest.webmanifest
   ```

   `init` writes an Android project and a signing keystore. The starting point checked into this repo is [`play/twa-manifest.json`](play/twa-manifest.json). Replace `REPLACE_WITH_YOUR_HOST` before you rely on that file, and keep the package id (`gif.photo.mydigitalcloset`) unless you are sure you will never ship it. The package id cannot be changed after the first upload.

3. **Signing.** Bubblewrap creates `android.keystore`. Back it up somewhere that is not the git repo. Losing it before Play App Signing is turned on means you cannot update the app. Build the bundle:

   ```bash
   bubblewrap build
   ```

   Upload the `.aab` to Play. Turn on **Play App Signing**. Play then holds the app signing key and you keep the upload key. You can see the certificates under **Play Console → App integrity**.

4. **Digital Asset Links.** The installed Play app is allowed to open your site full-screen only if `https://YOUR-HOST/.well-known/assetlinks.json` lists the app. Put the SHA-256 of the **Play app signing certificate** into [`web/.well-known/assetlinks.json`](web/.well-known/assetlinks.json), deploy the site again, and check it in [Google’s statement list tester](https://developers.google.com/digital-asset-links/tools/generator). A local upload-key fingerprint is not enough once Play App Signing is on.

5. **Store listing.** Use the phone screenshots, the short description, and the privacy policy URL `https://YOUR-HOST/privacy.html`. In the **Data safety** form, say the app collects nothing and shares nothing: the wardrobe is stored on the device by the browser, and the developer’s servers do not receive it.

6. **Closed test, then production.** New personal Play accounts have to run a closed test before production access is granted. Create a closed testing track, add at least **12 testers**, and have them opt in and install the app. Google asks that this track stay in good standing for **14 days**. After that, apply for production. The exact checklist is in Play Console and Google does change it, so read the banner in the console before you rely on the numbers.

The computer app does not go through Play. Only the site does.

# My Digital Closet

A private wardrobe you can open from a link on an iPhone or an Android phone, and also keep on your computer. Clothes and photos stay on the device. Nothing is uploaded to a closet server.

## Use it on a phone

Open the site in Chrome or Safari. The address is the link you publish with the steps below. That link is the app. The Play build, further down, is a separate Android package of these same pages.

- **Android:** the browser offers **Install**, or you can use the menu and choose **Add to Home screen** or **Install app**. That uses the site as an app. No Play Store is required for this step.
- **iPhone:** tap **Share**, then **Add to Home Screen**. iOS does not show the Android install button. The home-screen icon opens the same app.

The app works offline after the first visit. The closet itself is stored in the browser on that phone (IndexedDB). Deleting the home-screen icon does not always delete the data; clearing the site data for that address does.

### Import clothes from photos

Open **Import**. Choose photos, a folder (Chrome on Android and on a computer), or take a picture. The first scan downloads two open models into the browser, about 20 MB in total:

- [SegFormer B0 clothes](https://huggingface.co/Xenova/segformer_b0_clothes) (quantized, about 4 MB) finds a person and cuts out each garment. It is the small, phone-sized version of the same kind of model the computer app uses.
- [DINOv2 small](https://huggingface.co/Xenova/dinov2-small) (4-bit, about 15 MB) turns each crop into a signature so the same piece in another photo can be recognized. If that small file cannot load, the app tries the next size (about 24 MB).

That download is the model files only. The photos are not part of the request, and they are not sent to a vision API. Later scans use the cached models and run on the phone.

Photos do not need to stay large. Each one is turned upright, converted to sRGB, and shrunk to about 640 pixels on the long side before clothes are found. The color is measured from the garment pixels only — not the background or skin — on that 640-pixel photo, using k-means in CIELAB. You see a readable name, such as Blue, and the measured hex. That name and hex are saved before the picture is compressed, so the color does not depend on the stored file. The saved crop is a tight cutout of the garment on a plain background, as one WebP. **Small** is the default, about 384 pixels and roughly 20–40 KB. **Medium** is about 640 pixels and 50–100 KB. **High** is about 1024 pixels and 150–300 KB. A plain shirt lands lower than a detailed coat. The first time you open the app, before anything else, you pick Small, Medium, or High. That screen compares a sample outfit at each size, with the real file size of each piece and an estimate for about 1,000 items. The pick is saved and used for every import after that. Settings lets you change it, and the comparison there uses your own clothes. The color name is saved before that picture is compressed. If you change the size later, the app rebuilds the picture from the original photo when that file is still available. Otherwise it can only make a picture smaller. The closet does not keep a second thumbnail or a copy of the original photo.

The scan is built to run slowly and to keep what it has already finished:

- The queue remembers each photo by its path, size, and time. It does not store a copy of the original. If you picked individual files and then closed the page, those files have to be chosen again. A folder you already allowed can be read again. Finished pieces stay finished. The original file is never changed.
- **Scan next 4** does a short batch. **Scan all remaining** keeps going. **Stop after this photo** finishes the one in progress and leaves the rest queued.
- There is a short pause between photos so the phone can cool down. **Only scan while charging** waits when the phone is unplugged. Chrome and the Play app can see the charger. iPhone’s browser cannot, so that switch does not block a scan in Safari.
- **Keep the screen on during the scan** uses the screen wake lock while the app is open. It is off unless you turn it on.
- If the page is closed mid-scan, opening it again continues from the last finished photo. On iPhone the system pauses work in the background; the checkpoint is what makes it continue. Finished photos are not scanned again.

Nothing is added to the closet until you approve it. You can fix the name, category, color, and season first. A dress is stored as **Full Body** so a look can treat it as a one-piece, and its crop file goes in `dresses/`. The segmenter has no coat class, so a long top is only a suggestion of outerwear. Rejecting a guess drops the crop and remembers the signature. It does not delete the original photo, because the app never has permission to change files you did not pick as a save destination.

**Settings** is where you change the picture size. The comparison there uses your own clothes, and it also shows how much space the closet files use and the average size of a piece photo. **Clean up and reclaim space** deletes leftover copies of original photos from older versions of the app, drops a second crop when the piece already has one, and shrinks pictures that are still large. Names and colors stay as they are.

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

On the computer, **Import** reads a folder path. Crops go to a separate folder, never inside the photo folder. The computer models are SegFormer B2 and MobileNetV3-Small, saved in `model_cache/`. Originals are only read, telemetry from the model tools is turned off, and a scan can be resumed. Photos are shrunk to about 640 pixels before the model runs. Each crop is one WebP at the picture size you choose: Small, Medium, or High. The color is the garment’s measured name plus hex, saved before the file is compressed. The first time you open the app you choose Small, Medium, or High on a sample outfit, with file sizes and a storage estimate. That choice is the default for every import. Storage on the Import page lets you change it, and the comparison there uses your own clothes. **Clean up and reclaim space** drops extra files and can make pictures smaller. It does not enlarge a picture when the original photo is gone. Photos that do not live in `closet_images/` are left alone.

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

Use this when you want a link to send people. The Play app, further down, packages the same pages inside an Android app and does not need this host to keep running.

1. Create a free [Cloudflare Pages](https://pages.cloudflare.com/) project.
2. Upload the contents of `web/` as the site root, or connect this GitHub repo and set the root directory to `web`.
3. The project gives you an address such as `https://my-digital-closet.pages.dev`. That address is the link you send people.

### GitHub Pages

1. Push this repo.
2. In the repo, open **Settings → Pages**.
3. Deploy from a branch. Use a branch whose root is the contents of `web/` (the `gh-pages` branch is the usual name), or set the site to serve the `web` folder if GitHub offers that.
4. The link looks like `https://YOUR-USER.github.io/my-digital-closet/`.

A project site on `github.io` is enough for the installable link and for iPhone.

## Google Play

The Play build is a [Capacitor](https://capacitorjs.com/) app. The same `web/` pages run inside an Android WebView, and a foreground service keeps a scan going when the app is not on screen. A Trusted Web Activity cannot do that: it is a Chrome window, and Chrome will not keep running the page’s work with a foreground service after you leave. The package id is `gif.photo.mydigitalcloset`. It cannot be changed after the first upload.

The service shows a progress notification (“Scanning 3 of 40”). It holds a partial wake lock only while a photo is actually being scanned, and lets the CPU sleep when the scan is waiting for the charger. Between photos the app waits a couple of seconds. If Android reports the phone is hot, the scan pauses and the notification says so. **Only scan while charging** is the option for battery and heat. Leaving with the Home button keeps the scan running. Swiping the app away stops the process; opening it again continues from the last finished photo. The photo that was in progress is retried. Finished photos are not lost.

`web/.well-known/assetlinks.json` is not used by this Play build. It would only matter for a Trusted Web Activity.

1. Pay the one-time **$25** [Play Console registration fee](https://play.google.com/console/signup) and finish identity verification. Google sometimes holds new accounts for a few days.
2. Install a JDK, Android Studio (or the command-line SDK), and the repo dependencies:

   ```bash
   npm install
   npx cap sync android
   ```

   The Android project is already in `android/`. `npx cap sync android` copies `web/` into it. You need that after any change to the pages.

3. **Signing.** Create an upload keystore and do not commit it:

   ```bash
   keytool -genkeypair -v -keystore closet-upload.keystore -alias closet -keyalg RSA -keysize 2048 -validity 10000
   ```

   Copy `keystore.properties.example` to `keystore.properties` and fill in the passwords and the path to the keystore. Back up the keystore somewhere that is not the git repo. Losing it before Play App Signing is turned on means you cannot update the app. Build the bundle:

   ```bash
   cd android && ./gradlew bundleRelease
   ```

   The bundle is `android/app/build/outputs/bundle/release/app-release.aab`. Upload it to Play. Turn on **Play App Signing**. Play then holds the app signing key and you keep the upload key. Certificates are under **Play Console → App integrity**.

4. **Store listing.** Use the phone screenshots, the short description, and the privacy policy URL. That page is `web/privacy.html` on the public site, for example `https://YOUR-HOST/privacy.html`. In the **Data safety** form, say the app collects nothing and shares nothing. The wardrobe stays on the device. The notification exists only so Android can keep a scan running. Declare the foreground service type as data sync: the user started a scan of photos already on the phone.

5. **Closed test, then production.** New personal Play accounts have to run a closed test before production access is granted. Create a closed testing track, add at least **12 testers**, and have them opt in and install the app. Google asks that this track stay in good standing for **14 days**. After that, apply for production. The exact checklist is in Play Console and Google does change it, so read the banner in the console before you rely on the numbers.

The computer app does not go through Play. The link from the section above does not go through Play either. Only this Android bundle does.

On the computer, photo import already resumes. `python photo_import.py scan` records each finished picture and skips it the next time.

# ASHFALL

A browser-playable Pygame game.

## Play online

After GitHub Pages finishes its first deployment, the game will be available at:

`https://YOUR-GITHUB-USERNAME.github.io/YOUR-REPOSITORY-NAME/`

## Publish it on GitHub

1. Create a new GitHub repository. A good name is `ashfall`.
2. Upload everything in this folder, including the `.github` folder.
3. Make sure the default branch is named `main`.
4. Open the repository's **Settings → Pages**. Under **Build and deployment**, select **GitHub Actions** if GitHub asks for a source.
5. Go to the **Actions** tab. The `Build and deploy Ashfall` workflow should run automatically.
6. When it finishes successfully, open the Pages URL shown by the workflow.

The workflow builds the Pygame game with PyGBAG and deploys the generated browser files to GitHub Pages.

## Local desktop version

Install Python and pygame-ce, then run:

```bash
python -m pip install -r requirements.txt
python main.py
```

## Game balance

The realm recommendation thresholds in this version are:

- Ember Realm: 8+
- Frozen Realm: 20+
- Void Realm: 28+
- Starfall Realm: 36+

The recommendation values propagate to the realm warnings, NPC guidance, boss guidance, secret-boss guidance, and HUD difficulty indicator.

## Browser compatibility

The web build uses PyGBAG/pygame-wasm and requires a modern browser with WebAssembly support. The first load can take longer while the browser downloads and caches the runtime.

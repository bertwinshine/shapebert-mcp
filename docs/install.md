# Install ShapeBert

Official source: github.com/bertwinshine/shapebert-mcp. Verify releases with:
`gh release verify v1.0.0 -R bertwinshine/shapebert-mcp`

## Where it works

FreeCAD 1.1 has to run on the same computer as the AI client:
- **Claude Code** (paid Claude plans): tested.
- **Claude Desktop** through the [manual local-server setup](#manual-setup-windows)
  (works on the Free plan, with its limited usage): not tested yet.

It doesn't work in claude.ai in the browser or in the mobile app: those run in the
cloud and can't reach FreeCAD on your PC. Tested on Windows; the unit tests also run
on Linux.

## Install as a Claude plugin

You need FreeCAD 1.1 and [uv](https://docs.astral.sh/uv/getting-started/installation/)
(on Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`).

1. In Claude Code, add this repository as a plugin source and install the plugin:

   ```
   /plugin marketplace add bertwinshine/shapebert-mcp
   /plugin install shapebert-mcp@bertwinshine
   ```

   The first start takes a few seconds while uv installs the pinned dependencies.
2. Ask Claude to run `doctor`. FreeCAD won't be reachable yet, and the report gives
   the exact path of `install_autostart.FCMacro` on your computer.
3. In FreeCAD, open that file with File > Open and press Execute macro, then
   restart FreeCAD. The Report view should show
   `[FreeCAD MCP listener 1.1.0] listening on 127.0.0.1:9876`.
4. Ask for a part, for example "a flange, OD 120, 12 thick, 40 bore, six M8 holes
   on a 90 mm pitch circle".

After a plugin update, `doctor` tells you when FreeCAD still runs the old listener;
run the macro again and restart FreeCAD.

## Install from FreeCAD's Addon Manager

The FreeCAD side can also come from FreeCAD's Addon Manager. ShapeBert isn't in
FreeCAD's add-on index yet, so add it as a custom repository first:

1. In FreeCAD 1.1, open Edit > Preferences > Addon Manager. Under "Custom
   repositories", click the add button, fill in these two fields, then OK:

   Repository URL: `https://github.com/bertwinshine/shapebert-mcp`
   Branch: `main`

2. Open Tools > Addon Manager, find **shapebert-mcp**, click Install, and restart
   FreeCAD. The add-on goes to the `Mod` folder in FreeCAD's user folder (run
   `App.getUserAppDataDir()` in the Python console to see where that is; on Windows
   it is usually `%APPDATA%\FreeCAD\v1-1\Mod\shapebert-mcp`).
3. After the restart, FreeCAD asks once whether to start the ShapeBert bridge, and
   warns that connected AI agents can run code with your account's permissions.
   **Don't start** is the default. Choose **Start with FreeCAD** to start it now and
   with every FreeCAD start. To change your answer later, run Macro > Macros... >
   `ShapeBert_Bridge` (the Addon Manager puts it in your Macros folder; the
   `install_autostart.FCMacro` it copies there as well is for the plugin setup and
   isn't needed here).

If you installed the listener with `install_autostart.FCMacro` before, delete
`Mod/FreeCADMCP` in FreeCAD's user folder, so only one copy starts.

The MCP server runs outside FreeCAD, started by your AI client from the add-on
folder with [uv](https://docs.astral.sh/uv/getting-started/installation/), which
installs the pinned dependencies into the add-on folder on first start. Replace
`<ADDON>` with the add-on folder from step 2.

- Claude Code:

  ```
  claude mcp add shapebert --scope user -- uv run --frozen --project "<ADDON>" "<ADDON>/server.py"
  ```

- Claude Desktop and other MCP clients, in their `mcpServers` setting:

  ```json
  {
    "mcpServers": {
      "shapebert": {
        "command": "uv",
        "args": ["run", "--frozen", "--project", "<ADDON>", "<ADDON>/server.py"]
      }
    }
  }
  ```

Then ask the assistant to run `doctor`. The Claude plugin also gives Claude the
working rules in `skills/shapebert/SKILL.md`; with another client, add that file to
its instructions. After an update in the Addon Manager, restart FreeCAD and your AI
client.

## Manual setup (Windows)

1. Install FreeCAD 1.1 and clone this repository.
2. `pip install --require-hashes -r requirements.lock`. This installs the exact
   versions the tests ran with, and pip refuses any file whose checksum doesn't
   match. (`requirements.txt` holds the one direct dependency, version 1 of the MCP
   SDK; version 2 renamed the classes the server uses.) With uv, `uv sync --frozen`
   does the same from `uv.lock`.
3. Copy `.mcp.example.json` to `.mcp.json` and point it at your Python and at
   `server.py`.
4. In FreeCAD, open `install_autostart.FCMacro` with File > Open and press
   Execute macro, then restart FreeCAD. This installs a small add-on with a copy of
   the listener that starts every time FreeCAD opens. If you'd rather not install
   the add-on, run `freecad_listener.py` as a macro in each session.
5. Start Claude Code in this folder, or add the `mcpServers` block to Claude
   Desktop, and ask it to ping FreeCAD.

Free-form code (`run_freecad_code`) is off by default, and the Build tools cover
most parts without it. Read ["Switching free-form code on"](security.md#switching-free-form-code-on)
before you change that.

Optional add-ons are not needed for the core tools. FCGear adds bevel, worm and
other special gears, SheetMetal adds parts folded in several directions, and
Fasteners adds 3D bolts and nuts. Ask the assistant to run `doctor`: it lists what
is installed, what each add-on adds and how to install it. The assistant never
installs anything itself.

## Tests

```
pip install pytest
pytest
```

The unit tests need no FreeCAD and run in a few seconds. The integration tests
need a running listener and are skipped otherwise. To run them without the GUI:

```
set FREECAD_MCP_HEADLESS=1
set FREECAD_MCP_HEADLESS_CODE=1
"C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe" -c "import runpy; runpy.run_path('freecad_listener.py', run_name='__main__')"
pytest tests/integration
```

Run this from the repository folder. `freecadcmd freecad_listener.py` would look
like the same thing, but freecadcmd imports a `.py` file by its module name, so an
installed copy of the listener (`Mod/FreeCADMCP`, or an Addon Manager install) runs
instead of this one. `runpy.run_path` loads exactly this file.

`FREECAD_MCP_HEADLESS_CODE=1` lets this headless listener run the tests' scripts
without the approval dialog (see ["The approval dialog"](security.md#the-approval-dialog)). Set it only for tests
and CI. Against FreeCAD with its GUI, every test script would wait for the dialog.

They close every open FreeCAD document, so save your work first. Among other
things they check large messages, parallel calls, timeouts, rollback after a
failed script, hole counting, a STEP export and re-import, parametric rebuilds,
hydrostatics against hand calculations for a box hull and a catamaran, and that
every saved example still builds. GitHub Actions runs the unit tests on Windows
and Linux and the integration tests on headless FreeCAD 1.1.

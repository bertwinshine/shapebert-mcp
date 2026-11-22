# ShapeBert – AI CAD + FEA assistant for FreeCAD

Official source: github.com/bertwinshine/shapebert-mcp. Verify releases with:
`gh release verify v1.0.0 -R bertwinshine/shapebert-mcp`

An MCP server that lets Claude design parts in FreeCAD from a plain-language
description. Before it builds anything it works out which engineering field the
request belongs to, asks for any dimension it shouldn't guess, and runs the
relevant calculations. After building, it checks the result: whether the solid is
valid, its measurements, a screenshot, and field-specific checks such as
hydrostatics for hulls or overhangs for printed parts. When you correct a part,
the fix is saved as an example for next time.

A generic FreeCAD bridge only gives the model a way to run code. Most of this
project is the engineering knowledge around that: seven domain files, calculators
for the maths, and checks that run inside FreeCAD.

## How it fits together

```
you ── Claude (follows skills/shapebert/SKILL.md)
         ├── knowledge/          domain rules, conventions, saved examples
         ├── cadkit/calculators  gear, sheet-metal, boat, weld, fastener, shaft maths
         └── server.py ──TCP──>  freecad_listener.py inside FreeCAD
                                 (runs code and cadkit/fc_tools.py checks)
```

`freecad_listener.py` runs inside FreeCAD and executes code on FreeCAD's main
thread. `server.py` is the MCP server that Claude starts. They talk over
`127.0.0.1:9876` with length-prefixed JSON messages.

A job that runs past its timeout isn't lost: it keeps running, and
`get_job_result` fetches its report when it's done. Long printed output comes back
cut to its end, and `get_job_result` pages through all of it.

## Tools

| Group | Tools |
|---|---|
| Bridge | `ping_freecad`, `get_status`, `doctor`, `run_freecad_code`, `get_job_result`, `get_document_info` |
| Build | `create_box`, `create_cylinder`, `set_placement`, `bind_parameters`, `pattern_polar`, `pattern_linear`, `boolean`, `fillet_edges`, `chamfer_edges` |
| Checking | `check_geometry`, `check_model_structure`, `measure`, `inspect_object`, `get_view`, `compare_shapes` |
| Files | `export_model`, `import_model`, `save_document` |
| Parameters | `set_parameters` |
| Builders | `build_spur_gear`, `build_ring_gear`, `build_sheet_profile` |
| Domain checks | `hydrostatics`, `check_printability` |
| FEA (CalculiX) | `fea_setup`, `fea_run`, `fea_results`: linear static (stress, displacement, reactions, safety factor), modal (natural frequencies), steady and transient heat conduction (temperatures, heat flow), thermal stress, linear buckling |
| Calculators | `calc_gears`, `calc_sheet_metal`, `calc_boat`, `calc_weld`, `calc_fasteners`, `calc_shafts`, `calc_flanges` |
| Knowledge | `match_domain`, `list_knowledge`, `read_knowledge`, `search_examples`, `save_example`, `log_correction` |

The Build tools make plates, flanges, bolt circles, rows of holes or slots, fillets
and chamfers without free-form code. They take numbers and object names only, make
parametric FreeCAD objects (Part::Cut, Draft arrays, Part::Fillet ...), and
`bind_parameters` ties their sizes and counts to the Params spreadsheet, so changing
one value later rebuilds the part.

`run_freecad_code` runs each script in a fresh namespace and returns the result,
any printed output, and a summary of every object the script created. If the
script fails, the objects it created are removed again. `export_model` handles
STEP, IGES, BREP, STL, 3MF and OBJ. `compare_shapes` reports the overlap of two
solids as volume of intersection over volume of union, so 1.0 means identical.

The server also exposes the knowledge files as MCP resources
(`knowledge://domains/{name}`, `knowledge://examples/{name}`,
`knowledge://conventions`) and four prompts: `design_part`, `design_boat`,
`review_part` and `learn_from_correction`.

## Domains

| Domain | Calculator | Checks in FreeCAD |
|---|---|---|
| Boat building for LSAM | `calc_boat` | `hydrostatics`, `check_printability` (lsam) |
| Gears and power transmission | `calc_gears`, including a planetary tooth-count solver | `measure` |
| Sheet metal | `calc_sheet_metal`: bend allowance, flat length, press-brake force | `measure` |
| Weldments | `calc_weld`: fillet weld capacity, throat size, tube mass | `measure` |
| Fasteners, holes and fits | `calc_fasteners`: ISO 273 holes, tap drills, counterbores, ISO 286 fits | `measure` counts holes by diameter |
| Shafts, keys and bearings | `calc_shafts`: shaft diameter, DIN 6885 keys, ISO 281 bearing life | `measure` |
| FDM 3D printing | | `check_printability` (fdm) |

To add a domain, copy `knowledge/domains/_template.md`, fill it in, and add a row
to `knowledge/domains/_index.md`. Nothing else needs to change.

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
   `[FreeCAD MCP listener 1.0.0] listening on 127.0.0.1:9876`.
4. Ask for a part, for example "a flange, OD 120, 12 thick, 40 bore, six M8 holes
   on a 90 mm pitch circle".

After a plugin update, `doctor` tells you when FreeCAD still runs the old listener;
run the macro again and restart FreeCAD.

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
most parts without it. Read "Switching free-form code on" below before you change
that.

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
"C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe" freecad_listener.py
pytest tests/integration
```

`FREECAD_MCP_HEADLESS_CODE=1` lets this headless listener run the tests' scripts
without the approval dialog (see "The approval dialog" below). Set it only for tests
and CI. Against FreeCAD with its GUI, every test script would wait for the dialog.

They close every open FreeCAD document, so save your work first. Among other
things they check large messages, parallel calls, timeouts, rollback after a
failed script, hole counting, a STEP export and re-import, parametric rebuilds,
hydrostatics against hand calculations for a box hull and a catamaran, and that
every saved example still builds. GitHub Actions runs the unit tests on Windows
and Linux and the integration tests on headless FreeCAD 1.1.

## Benchmark

`bench/` has 19 test prompts with hand-checked expected values. The v1 set gives
every dimension; the v2 set describes parts by standard and function (a DN50 PN16
flange, a pinion by module and ratio, a punt by payload, a DIN 6885 keyway). Four
prompts leave out a critical value, so the right answer is a question.
`bench/run_claude.py` sends the prompts to Claude Code and scores what ends up in
FreeCAD. See [bench/README.md](bench/README.md).

Results from 6 and 7 November 2026, one run per case, all 19 cases:

| Model | Setup | Mean score | Time per case | API cost, 19 cases |
|---|---|---|---|---|
| Opus 5.5 | This project (`full`) | 1.00 | 50 to 62 s | $6.07 |
| Opus 5.5 | Bare bridge (`bare`) | 1.00 | 35 to 38 s | $4.56 |
| Haiku | This project (`full`) | 1.00 | 52 s | $0.25 |
| Haiku | Bare bridge (`bare`) | 0.89 | 31 s | $0.14 |

Opus knows the standards and asks sensible questions on its own, so the knowledge
layer only makes it slower. Haiku is where the layer pays off: without it, Haiku
stops to ask about values that don't change the shape (the punt's material, the
exact hole positions on a wall hook) and fails those cases. With it, Haiku matches
Opus at about a twentieth of the cost. Details are in
[bench/README.md](bench/README.md).

The knowledge layer isn't tied to Claude. `bench/run_agent.py` gives other models
the same tools and rules through OpenRouter. Results from 11 November 2026, all 19
cases, `full` setup:

| Model | Kind | Mean score | Time per case | API cost, 19 cases |
|---|---|---|---|---|
| Gemma 4 31B | Open-weight (Google) | 0.92 to 0.96 | 48 to 50 s | $0.15 to $0.17 |
| Devstral | Mistral model | 0.79 | 70 s | $0.66 |
| GPT-OSS 120B | Open-weight (OpenAI) | 0.58 | 30 s | $0.04 |

Gemma 4 31B comes close to Haiku for less money, which is why it's the default
non-Claude model for further tests. Scores move between runs (a double run of all
19 cases gave Gemma 0.86, and a Haiku rerun on 12 November gave 0.95), so read
these as single-run snapshots, not rankings.

## Security and what it can do

ShapeBert lets an AI drive FreeCAD on your computer, so here is exactly what it can
reach and how to switch it off.

ShapeBert's limits apply only to ShapeBert's own tools. Your AI client's built-in
tools (shell, file access) are controlled by the client's own permission settings —
keep them on "ask".

### Where it listens

The listener inside FreeCAD binds to `127.0.0.1:9876` and nothing else, so other
computers on your network can't connect to it. Set `FREECAD_MCP_PORT` to use a
different port. The MCP server refuses to start if `FREECAD_MCP_HOST` points
anywhere but this computer (`127.0.0.1`, `localhost` or `::1`). Don't forward the
port on your router.

Every request is signed with a secret token. The listener makes a random one the
first time it starts and stores it in `~/.freecad_mcp/token` (on Windows
`C:\Users\<you>\.freecad_mcp\token`), created readable by your account only; the
MCP server reads the same file. Other programs on your PC, and web pages in your
browser, can't send code to FreeCAD without it. To keep it somewhere else, set
`FREECAD_MCP_TOKEN_FILE` to the same path for both FreeCAD and the server.

The token itself is never sent. Each request carries an HMAC-SHA256 signature over
the protocol version, a timestamp, a one-time random value (nonce) and a hash of the
message. The listener refuses requests that are unsigned, wrongly signed, changed on
the way, more than 30 s off its clock, or sent a second time. It signs every reply the
same way, and the server ignores a reply that fails the check, so a program that takes
over the listener's port can't feed it fake results. The token is never written to a
log.

If the server and the listener in FreeCAD are different versions (for example after
a plugin update), `doctor` says so and gives the path of `install_autostart.FCMacro`
to run again.

### Free-form code

`run_freecad_code` runs any Python it is given inside FreeCAD, and FreeCAD's Python
can do anything your user account can. That's why it is off by default; the other
tools only run fixed code that ships with the plugin, and the Build tools take
numbers and names, never code.

#### Switching free-form code on

The risk in plain words: with free-form code on, anything the assistant reads can try
to make it run a program on your computer. That includes a part file, a web page or
a document. A script like that could read, change or delete your files. Switch it on
only if you need it, keep the permission prompts on and read each script before you
allow it.

With the plugin, put the switch in your own Claude Code settings,
`~/.claude/settings.json` (on Windows `C:\Users\<you>\.claude\settings.json`):

```json
{
  "env": {
    "FREECAD_MCP_ALLOW_CODE": "1"
  }
}
```

Merge the `env` block into what is already in that file, then restart Claude Code.
`doctor` should now report `free_form_code: on`. To switch it off again, remove the
line and restart. Don't edit the files in the plugin's folder
(`.claude-plugin/plugin.json`): every plugin update replaces them. Claude Code also
passes this setting to the other programs it starts. Nothing else reads this variable.

With the manual setup, add `"FREECAD_MCP_ALLOW_CODE": "1"` to the `env` block of the
server in your `.mcp.json` instead.

Even when it is on, scripts may only import FreeCAD's CAD modules (`FreeCAD`, `Part`,
`Sketcher`, `PartDesign`, `Draft`, `Spreadsheet`, `Fem`, `Mesh` and a few more) and
plain maths and data modules (`math`, `collections`, `json`, `re` and
similar). Any other import is refused before it gets to FreeCAD, and so are
`getattr`, `vars`, `open`, `eval`, `exec` and their kind, double-underscore names
and attributes, and FreeCAD's `doCommand`/`runCommand`, which run text as Python.
CAD code doesn't need any of that, and it's what an injected prompt would use to run
programs, delete files or send your data somewhere. Treat this as a speed bump, not
a sandbox: FreeCAD's own modules can still read and write files, and a determined
script may still find a way round the checks. If you really need other modules,
set `FREECAD_MCP_ALLOW_SYSTEM=1` as well, in the same place. Saved examples are checked either way,
with no switch, because future sessions copy their code.

Prompt injection is the main risk with any AI tool: a downloaded STEP file, a web
page or a shared document can contain text written to talk the assistant into
running something. Keep your AI client's permission prompts on, read what
`run_freecad_code` is about to run, and leave free-form code off when you work with
files from people you don't know.

#### The approval dialog

With free-form code on, FreeCAD asks you about every script before it runs. Once the
import checks pass, `run_freecad_code` (and the test run in `save_example`) opens a
dialog in FreeCAD that shows the code, with three buttons:

- **Run once** runs this script. The next one asks again.
- **Allow for this FreeCAD session** runs this script and every later one until you
  close FreeCAD.
- **Cancel** (the default, also Esc or closing the window) refuses it.

With no answer in 120 s, the script is refused. FreeCAD keeps working while the
dialog is open; other requests wait in line until you answer. Each answer is written
to `logs/code_log.jsonl` in the work folder, next to the code it belongs to. The
dialog sits inside FreeCAD, outside the AI client, so a prompt injection that gets
past your client's permission prompt still has to get past you.

FreeCAD without its GUI (`freecadcmd`) can't show the dialog, so it refuses
free-form code. For automated tests only, start the listener with
`FREECAD_MCP_HEADLESS_CODE=1` to let it run scripts without asking.

### Files, network and logs

- File tools only read and write inside one work folder, `~/FreeCAD_MCP_work` by
  default (set `FREECAD_MCP_WORKDIR` to move it), and only model and FreeCAD file
  types. Paths outside it, including tricks with `..` or links, are refused.
- The plugin also writes to the knowledge folder when you save an example or log a
  correction. The FreeCAD macro, if you run it, installs a small add-on into
  FreeCAD's `Mod` folder.
- No network. The MCP server only talks to FreeCAD on your own computer. The one
  download is on first start, when uv fetches the pinned Python packages listed in
  `uv.lock` from PyPI.
- No telemetry. Nothing about you or your parts is collected or sent anywhere. Your
  prompts and the tool results do go to the AI model you use in Claude, as with any
  other tool.
- `fea_run` makes FreeCAD start Gmsh and CalculiX (`ccx`), two local programs that
  come with FreeCAD. Their files go to `fea/<analysis name>` in the work folder and
  to FreeCAD's temp folder. Neither uses the network.
- Logs: every free-form script (run or refused) is appended to
  `~/FreeCAD_MCP_work/logs/code_log.jsonl`, corrections go to `corrections.jsonl` in
  your knowledge folder, and the listener prints its start-up line to FreeCAD's
  Report view (or the console when headless).

### Stopping and uninstalling

The listener lives inside FreeCAD, so closing FreeCAD stops it and frees the port.
To stop it without closing FreeCAD, type `App._mcp_listener.stop()` in FreeCAD's
Python console.

Auto-start is opt-in: nothing starts with FreeCAD unless you ran
`install_autostart.FCMacro` yourself. To remove everything:

1. In FreeCAD's Python console, run `App.getUserAppDataDir()` to find FreeCAD's user
   folder, close FreeCAD, and delete `Mod/FreeCADMCP` in that folder.
2. Remove the plugin in Claude Code (for the manual setup, remove the server from
   `.mcp.json` instead):

   ```
   /plugin uninstall shapebert-mcp@bertwinshine
   ```

3. Delete `~/.freecad_mcp` (the token) and, if you don't want your exports and logs,
   `~/FreeCAD_MCP_work`.

### What each tool can do

Read-only tools only look at the model, the knowledge base or do maths. Tools that
change the model add or edit objects in the open FreeCAD document (and
`log_correction` adds a line to the correction log). Tools that can overwrite may
replace files in the work folder or knowledge folder, run arbitrary code, or
replace an earlier analysis. Your AI client sees the same three labels and can ask
you before the risky ones.

| Tool | Access |
|---|---|
| `ping_freecad`, `get_status`, `doctor`, `get_job_result` | Read-only |
| `get_document_info`, `inspect_object`, `measure` | Read-only |
| `check_geometry`, `check_model_structure`, `get_view` | Read-only |
| `compare_shapes`, `hydrostatics`, `check_printability` | Read-only |
| `calc_gears`, `calc_sheet_metal`, `calc_boat`, `calc_weld` | Read-only |
| `calc_fasteners`, `calc_shafts`, `calc_flanges` | Read-only |
| `match_domain`, `list_knowledge`, `read_knowledge`, `search_examples` | Read-only |
| `fea_results` | Read-only |
| `create_box`, `create_cylinder` | Changes model |
| `set_placement`, `bind_parameters`, `boolean` | Changes model |
| `pattern_polar`, `pattern_linear`, `fillet_edges`, `chamfer_edges` | Changes model |
| `build_spur_gear`, `build_ring_gear`, `build_sheet_profile` | Changes model |
| `set_parameters`, `import_model` | Changes model |
| `log_correction` | Changes model (appends to the correction log) |
| `run_freecad_code` | Can overwrite (runs any code, off by default) |
| `export_model`, `save_document` | Can overwrite (files in the work folder) |
| `save_example` | Can overwrite (an example, only with `overwrite=True`) |
| `fea_setup`, `fea_run` | Can overwrite (an analysis of the same name and its solver files) |

## Your own knowledge

`knowledge/` holds the shared rules, domain files and two starter examples. Your own
examples, corrections and designs belong in a separate folder: set
`FREECAD_MCP_EXTRA_KNOWLEDGE` to it (or create `knowledge-private/` next to
`knowledge/`). The server reads both, lets your files override shared ones with the
same name, and saves every new example and correction to your folder, so
`knowledge/` stays clean. Keep that folder out of any public repository.

## Known limits

- Multithreaded CalculiX builds can give unstable results. On CI the same buckling
  input gave load factors of 0.96, 8.4 and 1728 from run to run, and static runs
  sometimes failed the equilibrium check. ShapeBert therefore runs every CalculiX
  analysis single-threaded, which makes large meshes slower. `fea_run` and
  `fea_results` report the CalculiX binary, version and thread count that were used.

### Running CalculiX on more threads

You can opt in to more threads with `FREECAD_MCP_CCX_THREADS`. Set it in the `env`
block in the same place as `FREECAD_MCP_ALLOW_CODE` above, for example
`"FREECAD_MCP_CCX_THREADS": "4"`, then restart. Leave it unset for one thread.

Warning: with some CalculiX builds, more than one thread gives wrong results with no
error message. If you switch it on, solve one of your parts with and without it,
and compare the results first. Always check `equilibrium_ok`. If results change from
run to run, remove the setting.

## Roadmap

Done so far: the bridge, the knowledge base with the ask-first rule, the
correction loop, the checking tools, the calculators, and the hydrostatics and
printability checks. Next:

- [x] v0.5: quick FEM checks with CalculiX: linear static and modal
- [ ] FEA self-check suite and more analysis types (brackets, frames, gear teeth)
- [ ] v0.6: rebuild 3D parts from a 2D drawing or photo, scored with `compare_shapes`
- [ ] Listing in the Claude plugin directory and the FreeCAD Addon Manager, with an
      example gallery

## License

Apache License 2.0, see [LICENSE](LICENSE) and [NOTICE](NOTICE). You can use,
change and share the code, also commercially, as long as you keep the copyright
and NOTICE file and say what you changed.

My own designs, worked examples, corrections and test cases are not in this
repository. They are kept privately and are available on request for
collaborations.

To report a security problem, see [SECURITY.md](SECURITY.md).

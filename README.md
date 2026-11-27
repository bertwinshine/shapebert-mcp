# ShapeBert

Official source: github.com/bertwinshine/shapebert-mcp. Verify releases with:
`gh release verify v1.0.0 -R bertwinshine/shapebert-mcp`

ShapeBert is an MCP server for FreeCAD. Claude builds a part from your description,
and ShapeBert checks the result against that description before the part is
reported as done.

<!-- Demo GIF goes here: a request built in FreeCAD, its requirement checks passing,
     and an FEA run with its assumptions block. Save it as docs/demo.gif and link it. -->

## Why ShapeBert

The numbers in your request become checks on the part. "Six M10 holes on a 100 mm
pitch circle, 12 mm thick" is stored as a hole count, a hole diameter, a pitch circle
and a thickness, and `verify_requirements` measures each of them on the current
geometry. Positions are checked the same way, such as a bore centre 50 mm above the
base or holes 20 mm from an edge, and bolt holes also get a minimum edge distance and
hole spacing. While a check fails, the part isn't reported as finished; the report
shows what was measured next to what was asked for.

Each size has a recorded source. The driving dimensions sit in a Params spreadsheet
that the model is bound to, and every entry says where its value came from: your own
words, quoted exactly, a rule from a knowledge file, a calculator call, or a default.
`explain_params` lists them, and each report ends with the defaults so you can see
what was assumed and change it.

FEA results come with the assumptions behind them. Next to the stresses,
displacements, frequencies or temperatures, `fea_results` gives the element type, the
mesh size and node count, the material values and their source, each support and load
with the face it sits on, and the solver version. It warns when a stress peak sits on
a singularity, when a load is concentrated on a small area, and when the mesh hasn't
been checked. `fea_convergence` solves again on finer meshes and says which results
settled.

The FEA is tested against known answers. Textbook cases (a cantilever's deflection,
stress, frequency and buckling load, a bar in tension, heat conduction, thermal
expansion, a plate with a hole and a thick cylinder) and the NAFEMS LE1 benchmark are
solved with the same tools and compared within stated tolerances, and accepted results
are frozen so any change shows up. [docs/validation.md](docs/validation.md) has the
cases, their sources and the numbers.

Underneath are domain files for gears, sheet metal, fasteners, shafts, welds, boats,
3D printing and FEA, calculators so the arithmetic isn't done in the model's head, and
saved examples. ShapeBert asks before it guesses a critical dimension, and when you
correct a part, the fix is saved as an example for next time.

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
| Checking | `check_geometry`, `check_model_structure`, `measure`, `inspect_object`, `list_faces`, `get_view`, `compare_shapes`, `set_requirements`, `verify_requirements` |
| Files | `create_document`, `open_document`, `save_document`, `export_model`, `import_model` |
| Parameters | `set_parameters`, `explain_params` |
| Builders | `build_spur_gear`, `build_ring_gear`, `build_sheet_profile` |
| Domain checks | `hydrostatics`, `check_printability` |
| FEA (CalculiX) | `fea_setup`, `fea_run`, `fea_results`, `fea_convergence`: linear static (stress, displacement, reactions, safety factor), modal (natural frequencies), steady and transient heat conduction (temperatures, heat flow), thermal stress, linear buckling; every result with its assumptions and a mesh convergence check |
| Calculators | `calc_gears`, `calc_sheet_metal`, `calc_boat`, `calc_weld`, `calc_fasteners`, `calc_shafts`, `calc_flanges`, `calc_hand_check` |
| Knowledge | `match_domain`, `list_knowledge`, `read_knowledge`, `search_examples`, `save_example`, `log_correction` |

The Build tools make plates, flanges, bolt circles, rows of holes or slots, fillets
and chamfers without free-form code. They take numbers and object names only, make
parametric FreeCAD objects (Part::Cut, Draft arrays, Part::Fillet ...), and
`bind_parameters` ties their sizes and counts to the Params spreadsheet, so changing
one value later rebuilds the part.

FreeCAD numbers faces and edges in an order that changes when the part changes, so
`Face6` can be the top face of one plate and an end face of the next. Fillets,
chamfers and FEA setups therefore take selectors such as `top`, `-X`, `bore`,
`cylindrical faces radius 5.5`, `largest planar face`, `edges of top face`,
`vertical edges` or `concave edges`, found from the geometry with fixed tolerances.
A fillet or chamfer made from selectors keeps them and finds its edges again on
every rebuild. A selector that matches nothing, or ties (two faces of the same
largest area), is refused with the candidates. `list_faces` lists every face with
its type, centre, normal or axis and radius, and area. Documents with fillets made
from edge numbers still open and rebuild as before. A selector fillet needs
ShapeBert's `shapebert_selectors.py` to rebuild; without it FreeCAD keeps the last
shape.

`set_requirements` stores the numbers and features of the request as checks on the
part, each with the request's own words: overall size, hole count, hole diameter,
pitch circle, hole spacing, edge distance, thickness, volume or mass, and features that have to be
there (a fillet, a chamfer). They are saved with the document. `verify_requirements`
measures them on the current shape and lists each check as pass or fail with the
measured and required values, so "6 x M10 holes on PCD 100" is checked again after
every change instead of trusted. A check can also be a limit: `op` `"min"` for "at
least 3 mm wall", `"max"` for "under 2 kg" (the default `"eq"` takes a tolerance).
When no hole has the asked-for diameter, the check fails with the nearest hole sizes
measured (an M10 clearance hole drilled at 10.5 instead of 11 shows 10.5), not just
"not found". `edge_distance` measures each hole's centre to the nearest outer edge
of the part. Hole edge distance and hole pitch also get checks that come from a rule
instead of the request: their minimums are defined once, in `cadkit/hole_rules.py`
(rule `machined`, ShapeBert's default of 2 x the hole diameter; rule
`steel_structure`, EN 1993-1-8 Table 3.3: edge 1.2 x d0, pitch 2.2 x d0 along the load
and 2.4 x d0 across it, not yet checked against the standard text). `calc_fasteners`
returns them, and such a check names that calculation as its `source` instead of a
quote, so a hole too close to the edge shows up in `verify_requirements` with measured
and required values. Sizes are measured on the exact surfaces, not on the display mesh, which
cuts inside arcs. The selector `inclined planar faces` finds chamfers, but on a part
built at an angle it also matches flat faces that are not chamfers.
`create_document` and `open_document` start or reopen a part without free-form code.

Every value in the Params spreadsheet carries its source: `set_parameters` takes one
per parameter, either the request's own words (`prompt`), a knowledge file and the
heading of the rule (`knowledge`, both checked to exist), a calculator and its inputs
(`calc`), or a `default` and where it is defined. A change the user asks for later is
a `user edit`. The sources are saved with the document. `explain_params` lists each
parameter with its value, unit, source and detail, shows a value changed by hand in
the spreadsheet as a user edit, and lists every default as an assumption, so a
report says plainly which numbers were not given.

Every FEA result from `fea_results` comes with an `assumptions` block: the analysis
type, the element type and order (C3D10, second-order tetrahedra, by default), mesh
size, node and element count and the Gmsh version, the material values the analysis
used with their source, every support, load and temperature with the selector that
chose it and the face's centre and normal, the units, and the CalculiX version and
mesh and solve times. Its `warnings` list first-order elements, a concentrated load
(on a vertex, an edge, or a face less than 2 x mesh size across), a peak stress within
two mesh sizes of such a load, a fixed face or a sharp inside edge (a singularity that
grows as the mesh is refined; the reply then also gives the peak outside those zones),
a mesh that is not checked or not converged, and every default that was used.
`fea_convergence` solves the analysis again at 2.25 and 1.5 times its mesh size and
reports the change in each followed result: for static runs the displacement and the
peak stress outside the flagged zones, otherwise the first frequency, buckling factor
or heat flow. Under 2 % counts as converged, and the reply names which results
converged.

`calc_hand_check` gives the closed-form estimate to compare an FEA result with: axial
bar, cantilever with its shear deflection, Euler column with its K factor (and the
shear correction), thin and thick (Lame) cylinder, plate with a hole (Kt = 3), beam
natural frequency, plane-wall conduction and thermal expansion. Each answer names its
formula, assumptions, validity checks, how 3D FEA usually differs and the source.
`knowledge/domains/fea-mechanics.md` explains each of them, plus torsion,
singularities and mesh convergence.

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
| FEA and mechanics hand checks | `calc_hand_check`: closed-form estimates to compare FEA with | `fea_results`, `fea_convergence` |

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
"C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe" -c "import runpy; runpy.run_path('freecad_listener.py', run_name='__main__')"
pytest tests/integration
```

Run this from the repository folder. `freecadcmd freecad_listener.py` would look
like the same thing, but freecadcmd imports a `.py` file by its module name, so an
installed copy of the listener (`Mod/FreeCADMCP`, or an Addon Manager install) runs
instead of this one. `runpy.run_path` loads exactly this file.

`FREECAD_MCP_HEADLESS_CODE=1` lets this headless listener run the tests' scripts
without the approval dialog (see "The approval dialog" below). Set it only for tests
and CI. Against FreeCAD with its GUI, every test script would wait for the dialog.

They close every open FreeCAD document, so save your work first. Among other
things they check large messages, parallel calls, timeouts, rollback after a
failed script, hole counting, a STEP export and re-import, parametric rebuilds,
hydrostatics against hand calculations for a box hull and a catamaran, and that
every saved example still builds. GitHub Actions runs the unit tests on Windows
and Linux and the integration tests on headless FreeCAD 1.1.

## Validation

[docs/validation.md](docs/validation.md) compares the FEA tools with textbook answers
for six cases: a cantilever (tip deflection and bending stress, natural frequency,
Euler buckling), a bar in tension, a bar with steady heat conduction and a freely
heated bar. It also runs published benchmarks: NAFEMS LE1 (elliptic membrane, coarse
and fine mesh), a plate with a hole in tension (Kirsch, Kt = 3) and a thick cylinder
under internal pressure (Lame), each next to its `calc_hand_check` value where a
closed form applies. NAFEMS LE10 is listed but not run: `fea_setup` cannot yet hold a
curved face in x and y only, or an edge in z. Each case in `tests/validation/` holds its
setup, the source of the formula or published value, the tolerance and why, and the
accepted FEA result. `pytest tests/validation` runs them against a listener (about
4 minutes): every value has to be within its tolerance, and on the FreeCAD, CalculiX
and Gmsh versions a result was frozen with, it must not move by more than 1e-6
relative. `python tests/validation/report.py` writes the page again; with
`--freeze "reason"` it also accepts the new results (`--cases` limits that to some
cases). Citations marked "edition/section to be checked" still need that detail
confirmed against the book, and cases marked "description to be checked" say which
detail of the setup was missing.

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
`install_autostart.FCMacro` yourself or chose **Start with FreeCAD** after an Addon
Manager install. To remove everything:

1. In FreeCAD's Python console, run `App.getUserAppDataDir()` to find FreeCAD's user
   folder, close FreeCAD, and delete `Mod/FreeCADMCP` in that folder. For an Addon
   Manager install, uninstall **shapebert-mcp** in the Addon Manager instead.
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
| `get_document_info`, `inspect_object`, `list_faces`, `measure` | Read-only |
| `verify_requirements`, `explain_params` | Read-only |
| `check_geometry`, `check_model_structure`, `get_view` | Read-only |
| `compare_shapes`, `hydrostatics`, `check_printability` | Read-only |
| `calc_gears`, `calc_sheet_metal`, `calc_boat`, `calc_weld` | Read-only |
| `calc_fasteners`, `calc_shafts`, `calc_flanges`, `calc_hand_check` | Read-only |
| `match_domain`, `list_knowledge`, `read_knowledge`, `search_examples` | Read-only |
| `fea_results` | Read-only |
| `create_box`, `create_cylinder` | Changes model |
| `set_placement`, `bind_parameters`, `boolean` | Changes model |
| `pattern_polar`, `pattern_linear`, `fillet_edges`, `chamfer_edges` | Changes model |
| `build_spur_gear`, `build_ring_gear`, `build_sheet_profile` | Changes model |
| `set_parameters`, `import_model` | Changes model |
| `create_document`, `open_document`, `set_requirements` | Changes model |
| `log_correction` | Changes model (appends to the correction log) |
| `run_freecad_code` | Can overwrite (runs any code, off by default) |
| `export_model`, `save_document` | Can overwrite (files in the work folder) |
| `save_example` | Can overwrite (an example, only with `overwrite=True`) |
| `fea_setup`, `fea_run`, `fea_convergence` | Can overwrite (an analysis of the same name and its solver files) |

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
- [x] FEA validation against analytical answers ([docs/validation.md](docs/validation.md))
- [ ] More FEA analysis types and validation cases (brackets, frames, gear teeth)
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

# Security and what it can do

ShapeBert lets an AI drive FreeCAD on your computer, so here is exactly what it can
reach and how to switch it off.

ShapeBert's limits apply only to ShapeBert's own tools. Your AI client's built-in
tools (shell, file access) are controlled by the client's own permission settings —
keep them on "ask".

## Where it listens

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

## Free-form code

`run_freecad_code` runs any Python it is given inside FreeCAD, and FreeCAD's Python
can do anything your user account can. That's why it is off by default; the other
tools only run fixed code that ships with the plugin, and the Build tools take
numbers and names, never code.

### Switching free-form code on

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

### The approval dialog

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

## Files, network and logs

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

## Stopping and uninstalling

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

## What each tool can do

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

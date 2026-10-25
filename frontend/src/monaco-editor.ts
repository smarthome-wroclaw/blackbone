/**
 * The Monaco build boneIO actually uses: the editor API plus YAML, nothing else.
 *
 * Importing the `monaco-editor` barrel pulls in `editor.main.js`, which
 * registers four worker-backed language services (TypeScript, CSS, HTML, JSON)
 * and ~85 Monarch grammars. The config editor only ever opens YAML — monaco-yaml
 * supplies the language service and Monaco's YAML definition the highlighting — so
 * everything else was emitted into the dist and shipped to the device for
 * nothing (the TypeScript worker alone was 6.9 MB).
 *
 * Import this module instead of `monaco-editor` anywhere in the app. Adding a
 * language means adding its `languages/definitions/<lang>/register.js` import here.
 */
import 'monaco-editor/languages/definitions/yaml/register.js';

export * from 'monaco-editor/editor/editor.api.js';

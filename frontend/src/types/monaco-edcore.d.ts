/**
 * `editor.api.js` is Monaco's editor API entry: the same public API as
 * `monaco-editor`, with every editor contribution, but without the language
 * packs. It ships no typings of its own, so borrow the barrel's.
 */
declare module 'monaco-editor/editor/editor.api.js' {
  export * from 'monaco-editor';
}

declare module 'monaco-editor/languages/definitions/yaml/register.js';

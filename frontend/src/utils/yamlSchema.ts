import { DUMP_SCHEMA, defineScalarTag, nullCoreTag } from 'js-yaml';

/**
 * Dump schema that renders null as an empty value (`key:`) instead of `key: null`.
 *
 * js-yaml 4 expressed this as `dump(data, { styles: { '!!null': 'empty' } })`.
 * That option was removed in js-yaml 5, so the null tag is redefined with a
 * `represent` that emits an empty scalar.
 */
const nullAsEmptyTag = defineScalarTag('tag:yaml.org,2002:null', {
  ...nullCoreTag,
  represent: () => '',
});

export const YAML_DUMP_SCHEMA = DUMP_SCHEMA.withTags(nullAsEmptyTag);

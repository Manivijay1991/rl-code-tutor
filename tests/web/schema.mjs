// Test helper: the same JSON Schema subset as src/coding_tutor/schema.py, for the JS side of the contract.
// Not shipped to the browser.

const TYPES = {
  object: (v) => v !== null && typeof v === "object" && !Array.isArray(v),
  array: (v) => Array.isArray(v),
  string: (v) => typeof v === "string",
  integer: (v) => Number.isInteger(v),
  number: (v) => typeof v === "number",
  boolean: (v) => typeof v === "boolean",
  null: (v) => v === null,
};

function resolve(ref, root) {
  if (!ref.startsWith("#/")) throw new Error(`only local $ref is supported: ${ref}`);
  return ref.slice(2).split("/").reduce((node, part) => node[part], root);
}

/** Return every problem found (empty when `value` matches `schema`). */
export function validate(value, schema, root = schema, path = "$") {
  if (schema.$ref) return validate(value, resolve(schema.$ref, root), root, path);
  if (schema.anyOf) {
    return schema.anyOf.some((s) => validate(value, s, root, path).length === 0) ? [] : [`${path}: matches none of the allowed shapes`];
  }
  if (schema.type) {
    const types = [schema.type].flat();
    if (!types.some((t) => TYPES[t](value))) return [`${path}: expected ${types.join(" or ")}`];
  }
  if (schema.enum && !schema.enum.some((e) => e === value)) return [`${path}: must be one of ${JSON.stringify(schema.enum)}`];
  if ("const" in schema && value !== schema.const) return [`${path}: must be ${JSON.stringify(schema.const)}`];
  const problems = [];
  if (TYPES.object(value)) {
    for (const k of schema.required ?? []) if (!(k in value)) problems.push(`${path}: missing required '${k}'`);
    const props = schema.properties ?? {};
    const extra = schema.additionalProperties ?? true;
    for (const [k, item] of Object.entries(value)) {
      if (k in props) problems.push(...validate(item, props[k], root, `${path}.${k}`));
      else if (extra === false) problems.push(`${path}: unexpected property '${k}'`);
      else if (typeof extra === "object") problems.push(...validate(item, extra, root, `${path}.${k}`));
    }
  } else if (Array.isArray(value)) {
    if (value.length < (schema.minItems ?? 0)) problems.push(`${path}: needs at least ${schema.minItems} items`);
    if (schema.maxItems !== undefined && value.length > schema.maxItems) problems.push(`${path}: allows at most ${schema.maxItems} items`);
    if (schema.items) value.forEach((item, i) => problems.push(...validate(item, schema.items, root, `${path}[${i}]`)));
  } else if (typeof value === "string") {
    if (value.length < (schema.minLength ?? 0)) problems.push(`${path}: shorter than ${schema.minLength}`);
    if (schema.maxLength !== undefined && value.length > schema.maxLength) problems.push(`${path}: longer than ${schema.maxLength}`);
    if (schema.pattern && !new RegExp(schema.pattern).test(value)) problems.push(`${path}: does not match ${schema.pattern}`);
  } else if (typeof value === "number") {
    if (schema.minimum !== undefined && value < schema.minimum) problems.push(`${path}: below ${schema.minimum}`);
    if (schema.maximum !== undefined && value > schema.maximum) problems.push(`${path}: above ${schema.maximum}`);
  }
  return problems;
}

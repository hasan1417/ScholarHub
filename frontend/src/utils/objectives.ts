export const parseObjectives = (scope?: string | null) => {
  if (!scope) return []
  return scope
    .split(/\r?\n|•/)
    .map((value) => value.replace(/^\s*\d+[)\.\-\s]*/, '').trim())
    .filter(Boolean)
}

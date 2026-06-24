interface ClassInfo {
  name: string
  properties: Array<{ name: string; type: string; originalKey: string }>
}

function toCamelCase(value: string): string {
  return value.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase())
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

function readObject(jsonString: string): Record<string, unknown> {
  return JSON.parse(jsonString) as Record<string, unknown>
}

function getJavaType(value: unknown): string {
  if (typeof value === 'number') return Number.isInteger(value) ? 'Integer' : 'Double'
  if (typeof value === 'boolean') return 'Boolean'
  if (Array.isArray(value)) return 'List<Object>'
  if (typeof value === 'object' && value !== null) return 'Object'
  return 'String'
}

function getTypeScriptType(value: unknown): string {
  if (typeof value === 'number') return 'number'
  if (typeof value === 'boolean') return 'boolean'
  if (Array.isArray(value)) return 'unknown[]'
  if (typeof value === 'object' && value !== null) return 'Record<string, unknown>'
  return 'string'
}

function classInfoFromJson(jsonString: string, className: string): ClassInfo {
  const obj = readObject(jsonString)
  return {
    name: className,
    properties: Object.entries(obj).map(([key, value]) => ({
      name: toCamelCase(key),
      type: getJavaType(value),
      originalKey: key,
    })),
  }
}

export function jsonToJava(jsonString: string, className = 'Entity'): string {
  const info = classInfoFromJson(jsonString, className)
  const fields = info.properties.map((prop) => `  private ${prop.type} ${prop.name};`).join('\n')
  return `public class ${info.name} {\n${fields}\n}`
}

export function jsonToTypeScript(jsonString: string, interfaceName = 'Entity'): string {
  const obj = readObject(jsonString)
  const fields = Object.entries(obj)
    .map(([key, value]) => `  ${key}: ${getTypeScriptType(value)}`)
    .join('\n')
  return `interface ${interfaceName} {\n${fields}\n}`
}

export function jsonToCSharp(jsonString: string, className = 'Entity'): string {
  const info = classInfoFromJson(jsonString, className)
  const fields = info.properties
    .map((prop) => `  public ${prop.type} ${capitalize(prop.name)} { get; set; }`)
    .join('\n')
  return `public class ${info.name}\n{\n${fields}\n}`
}

export function jsonToPython(jsonString: string, className = 'Entity'): string {
  const info = classInfoFromJson(jsonString, className)
  const fields = info.properties.map((prop) => `    ${prop.name}: object`).join('\n')
  return `from dataclasses import dataclass\n\n@dataclass\nclass ${className}:\n${fields}`
}

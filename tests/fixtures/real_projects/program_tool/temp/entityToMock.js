"use strict";

function parseJavaEntity(entityCode) {
  const classRegex = /public\s+class\s+(\w+)\s*\{([\s\S]*)\}/g;
  const classes = [];
  let match;
  while ((match = classRegex.exec(entityCode)) !== null) {
    classes.push({ name: match[1], fields: parseJavaFields(match[2]) });
  }
  return classes;
}

function parseJavaFields(classBody) {
  const fieldRegex = /private\s+([A-Za-z0-9<>,\s]+)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*;/g;
  const fields = [];
  let match;
  while ((match = fieldRegex.exec(classBody)) !== null) {
    fields.push({ type: match[1].trim(), name: match[2] });
  }
  return fields;
}

function generateJsonBodyMock(entityCode) {
  const classes = parseJavaEntity(entityCode);
  return JSON.stringify({ mockType: "json body", className: classes[0]?.name, fields: classes[0]?.fields });
}

function generateFormMock(entityCode) {
  const classes = parseJavaEntity(entityCode);
  return (classes[0]?.fields || []).map((field) => `${field.name}=mock`).join("\n");
}

module.exports = {
  generateJsonBodyMock,
  generateFormMock,
};

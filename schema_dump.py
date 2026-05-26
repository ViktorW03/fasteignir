#!/usr/bin/env python3
"""
Dumps the full GraphQL schema from g.mbl.is/v1/graphql
and saves it as both raw JSON and human-readable SDL format.

Usage:
    python3 schema_dump.py
"""

import json
import requests

ENDPOINT = "https://g.mbl.is/v1/graphql"
HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://www.mbl.is",
    "Referer": "https://www.mbl.is/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/146.0.0.0 Safari/537.36",
}

INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    queryType { name }
    mutationType { name }
    subscriptionType { name }
    types {
      ...FullType
    }
    directives {
      name
      description
      locations
      args {
        ...InputValue
      }
    }
  }
}

fragment FullType on __Type {
  kind
  name
  description
  fields(includeDeprecated: true) {
    name
    description
    args {
      ...InputValue
    }
    type {
      ...TypeRef
    }
    isDeprecated
    deprecationReason
  }
  inputFields {
    ...InputValue
  }
  interfaces {
    ...TypeRef
  }
  enumValues(includeDeprecated: true) {
    name
    description
    isDeprecated
    deprecationReason
  }
  possibleTypes {
    ...TypeRef
  }
}

fragment InputValue on __InputValue {
  name
  description
  type { ...TypeRef }
  defaultValue
}

fragment TypeRef on __Type {
  kind
  name
  ofType {
    kind
    name
    ofType {
      kind
      name
      ofType {
        kind
        name
        ofType {
          kind
          name
          ofType {
            kind
            name
            ofType {
              kind
              name
              ofType {
                kind
                name
              }
            }
          }
        }
      }
    }
  }
}
"""


def type_ref_to_str(t):
    """Recursively convert a TypeRef to a SDL type string like String!, [Int!]!"""
    if t is None:
        return "Unknown"
    kind = t.get("kind")
    name = t.get("name")
    of_type = t.get("ofType")

    if kind == "NON_NULL":
        return f"{type_ref_to_str(of_type)}!"
    elif kind == "LIST":
        return f"[{type_ref_to_str(of_type)}]"
    else:
        return name or "Unknown"


def schema_to_sdl(schema_data):
    """Convert introspection JSON to readable SDL-like text."""
    lines = []
    types = schema_data["__schema"]["types"]

    # Filter out built-in types
    user_types = [
        t for t in types
        if t["name"] and not t["name"].startswith("__")
        and t["kind"] not in ("SCALAR",)
        and t["name"] not in ("Boolean", "String", "Int", "Float", "ID")
    ]

    for t in sorted(user_types, key=lambda x: x["name"]):
        kind = t["kind"]
        name = t["name"]

        if kind == "OBJECT":
            lines.append(f"\ntype {name} {{")
            for field in (t.get("fields") or []):
                type_str = type_ref_to_str(field["type"])
                desc = f"  # {field['description']}" if field.get("description") else ""
                args = field.get("args", [])
                if args:
                    arg_strs = ", ".join(
                        f"{a['name']}: {type_ref_to_str(a['type'])}" for a in args
                    )
                    lines.append(f"  {field['name']}({arg_strs}): {type_str}{desc}")
                else:
                    lines.append(f"  {field['name']}: {type_str}{desc}")
            lines.append("}")

        elif kind == "INPUT_OBJECT":
            lines.append(f"\ninput {name} {{")
            for field in (t.get("inputFields") or []):
                type_str = type_ref_to_str(field["type"])
                lines.append(f"  {field['name']}: {type_str}")
            lines.append("}")

        elif kind == "ENUM":
            lines.append(f"\nenum {name} {{")
            for val in (t.get("enumValues") or []):
                lines.append(f"  {val['name']}")
            lines.append("}")

        elif kind == "INTERFACE":
            lines.append(f"\ninterface {name} {{")
            for field in (t.get("fields") or []):
                type_str = type_ref_to_str(field["type"])
                lines.append(f"  {field['name']}: {type_str}")
            lines.append("}")

    return "\n".join(lines)


def main():
    print("Fetching full schema from g.mbl.is...")
    resp = requests.post(
        ENDPOINT,
        headers=HEADERS,
        json={"query": INTROSPECTION_QUERY},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if "errors" in data:
        print("GraphQL errors:", json.dumps(data["errors"], indent=2))
        return

    # Save raw JSON
    with open("schema_raw.json", "w", encoding="utf-8") as f:
        json.dump(data["data"], f, indent=2, ensure_ascii=False)
    print("✓ Saved schema_raw.json")

    # Save human-readable SDL
    sdl = schema_to_sdl(data["data"])
    with open("schema.graphql", "w", encoding="utf-8") as f:
        f.write(sdl)
    print("✓ Saved schema.graphql")

    # Print a summary of user-facing types
    types = data["data"]["__schema"]["types"]
    user_types = [
        t for t in types
        if t["name"] and not t["name"].startswith("__")
        and t["kind"] == "OBJECT"
        and t["name"] not in ("Boolean", "String", "Int", "Float", "ID")
    ]
    print(f"\nFound {len(user_types)} object types:")
    for t in sorted(user_types, key=lambda x: x["name"]):
        field_count = len(t.get("fields") or [])
        print(f"  {t['name']} ({field_count} fields)")


if __name__ == "__main__":
    main()
import json
import os

# Configuration
FILES_TO_BUNDLE = {
    "mock_app.py": "mock_app.py",
    "app.py": "../app.py",
    "demo_data.json": "demo_data.json"
}
OUTPUT_FILE = "index.html"

def build():
    bundled_files = {}

    for virtual_path, local_path in FILES_TO_BUNDLE.items():
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                # We store the raw content as a string
                bundled_files[virtual_path] = f.read()
        else:
            print(f"⚠️ Warning: {local_path} not found.")

    # Convert our file dictionary to a JS-safe JSON string
    files_json = json.dumps(bundled_files)

    html_template = f"""<!doctype html>
<html>
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no" />
    <title>Job Fit Analyzer</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@stlite/browser@1.0.0/build/stlite.css" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module">
      import {{ mount }} from "https://cdn.jsdelivr.net/npm/@stlite/browser@1.0.0/build/stlite.js";
      
      mount({{
        theme: {{base: "dark"}},
        requirements: ["pandas"],
        entrypoint: "mock_app.py",
        files: {files_json}
      }}, document.getElementById("root"));
    </script>
  </body>
</html>"""

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html_template)
    
    print(f"✅ Modern Build Success! {OUTPUT_FILE} created.")

if __name__ == "__main__":
    build()
---
# This template will automatically load every time you open a Pull Request.
---

## 🛠 Type of Change
- [ ] 🐛 Bug fix (non-breaking change which fixes an issue)
- [ ] 🚀 New feature (non-breaking change which adds functionality)
- [ ] 🧹 Refactoring / Tech Debt
- [ ] 📝 Documentation update

## 📝 Description
Provide a brief summary of the changes and which issue it relates to.

## 🧪 Deployment Checklist (Pre-Merge)
*These checks ensure the runner will pass.*
- [ ] **Streamlit Test:** Does the app run locally without errors? (`streamlit run main.py`)
- [ ] **Environment:** Have I added any new dependencies to pyproject.toml?
- [ ] **Pathing:** Are all image/data paths relative so they work on Codeberg Pages?
- [ ] **Labels:** Does the workflow file still point to the right runner?

## 📸 Screenshots (If applicable)
*Add any visual changes to the UI here.*

## 🔗 Related Issues
Fixes # (issue number)
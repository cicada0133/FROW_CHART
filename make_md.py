import os

funcs = [
    "main", "inputLine", "inputInt", "inputYear", "inputChoice", 
    "printNode", "addToTree", "searchByCode", "minNode", "deleteNode", 
    "deleteTree", "traversePrintTree", "traverseLPK", "traverseSorted", 
    "saveTraverse", "findMinMaxYear", "countNodes", "storeNodesArr", 
    "buildBalancedArr", "rebalanceTree", "menuCreateTree", "menuAddNode", 
    "menuPrintTree", "menuPrintLPK", "menuDeleteNode", "menuDeleteRightSubtree", 
    "menuEditNode", "menuPrintSorted", "menuSaveToFile", "menuLoadFromFile", 
    "menuSearchByCode", "menuFindMinMaxYear", "printMenu"
]

md_content = "<div align=\"center\">\n\n# Блок-схемы\n\n"

for i, func in enumerate(funcs, 1):
    img_path = f"out_charts/{func}.png"
    caption = f"Рисунок 2.{i} – Блок-схема функции {func}"
    md_content += f"<img src=\"{img_path}\" alt=\"{func}\" style=\"max-width:80%; margin-bottom: 10px;\"><br>\n"
    md_content += f"<i>{caption}</i>\n\n<br><br><br>\n\n"

md_content += "</div>\n"

with open("flowcharts_list.md", "w", encoding="utf-8") as f:
    f.write(md_content)

print("Generated flowcharts_list.md")

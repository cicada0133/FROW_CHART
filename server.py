from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import tempfile
import os

from main_vertical import get_cpp_parser, process_compound, VerticalMainRenderer

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class RenderSettings(BaseModel):
    max_width: int = 200
    horiz_spacing: int = 2
    vert_spacing: int = 10
    padding: int = 3
    font_size: int = 79
    return_wide_route: bool = False
    fill_blocks: bool = True
    staggered_switch: bool = True

class CodeRequest(BaseModel):
    code: str
    global_settings: RenderSettings = None
    func_settings: dict[str, RenderSettings] = None

@app.post("/parse")
def parse_cpp_code(req: CodeRequest):
    parser = get_cpp_parser()
    tree = parser.parse(bytes(req.code, 'utf8'))
    
    functions = []
    
    def extract_funcs(node, code_bytes):
        if node.type == 'function_definition':
            decl = node.child_by_field_name('declarator')
            if decl:
                func_name = code_bytes[decl.start_byte:decl.end_byte].decode('utf-8')
                for c in decl.children:
                    if c.type == 'identifier':
                        func_name = code_bytes[c.start_byte:c.end_byte].decode('utf-8')
                        break
                        
                body = node.child_by_field_name('body')
                block_tuples = process_compound(body, code_bytes)
                
                if block_tuples:
                    data = [('start', 'Начало')] + block_tuples + [('end', 'Конец')]
                    
                    # Определяем, какие настройки применять к этой функции
                    current_settings = {}
                    if req.func_settings and func_name in req.func_settings:
                        current_settings = req.func_settings[func_name].model_dump()
                    elif req.global_settings:
                        current_settings = req.global_settings.model_dump()
                    
                    # Генерируем ГОСТ блок-схему с учетом настроек
                    is_staggered = current_settings.get('staggered_switch', True)
                    renderer = VerticalMainRenderer(staggered=is_staggered, config=current_settings)
                    renderer.render_nodes(data, is_first=True)
                    
                    # Сохраняем во временный SVG файл
                    temp_svg = tempfile.mktemp(suffix=".svg")
                    renderer.save(temp_svg)
                    
                    with open(temp_svg, "r", encoding="utf-8") as f:
                        svg_content = f.read()
                        
                    os.remove(temp_svg)
                    
                    functions.append({
                        "name": func_name, 
                        "svg": svg_content
                    })
                
        for c in node.children:
            extract_funcs(c, code_bytes)

    extract_funcs(tree.root_node, bytes(req.code, 'utf8'))
    
    return {"functions": functions}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)

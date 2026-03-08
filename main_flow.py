import sys
import os
import schemdraw
from schemdraw import flow
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from tree_sitter import Language, Parser

# Re-use the tree-sitter C++ parser setup
def get_cpp_parser():
    import tree_sitter_cpp as tscpp
    CPP_LANGUAGE = Language(tscpp.language())
    parser = Parser(CPP_LANGUAGE)
    return parser

class SpecializedMainRenderer:
    def __init__(self):
        self.d = schemdraw.Drawing()
        import logging
        logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)
        plt.rcParams['font.family'] = 'System'
        plt.rcParams['font.weight'] = 'bold'
        # Tighter settings for main flowchart
        self.d.config(fontsize=75, margin=2.5, lw=10, font='System')
        self.scale = 1.8
        self.axis_x = 0.0
        self.last_pos = (self.axis_x, 0)
        self.max_y = 0
        self.return_points = []
        self.blocks_bboxes = []
        self.merge_gap = 5.0

    def wrap_text(self, text, max_width=24):
        if not text: return ""
        import textwrap
        return "\n".join(textwrap.wrap(text, width=max_width))

    def add_block(self, ntype, label, at=None, skip_line=False):
        text = self.wrap_text(label)
        if at is None:
            at = self.last_pos

        if not skip_line:
            l = self.d.add(flow.Line().at(at).down(self.scale))
            at = l.end

        # Calculate dynamic width based on text
        lines = text.split('\n')
        max_len = max(len(ln) for ln in lines) if lines else 0
        w = max(21.0, max_len * 1.35 + 8.0)

        if ntype in ['start', 'end', 'Начало', 'Конец']:
            obj = flow.Start(at=at, label=text, w=w)
        elif ntype == 'decision' or ntype in ['if', 'while', 'for_loop']:
            obj = flow.Decision(at=at, label=text, w=w*1.5)

        elif ntype == 'io':
            obj = flow.Data(at=at, label=text, w=w+4.0)
        elif ntype == 'call':
            obj = flow.Subroutine(at=at, label=text, w=w)
        else:
            obj = flow.Box(at=at, label=text, w=w)
        
        obj = self.d.add(obj)
        self.blocks_bboxes.append({
            'x1': obj.NW[0], 'y1': obj.NW[1],
            'x2': obj.SE[0], 'y2': obj.SE[1]
        })
        self.last_pos = (obj.S[0], obj.S[1])
        self.max_y = min(self.max_y, self.last_pos[1])
        return obj

    def render_nodes(self, nodes, nest=0, is_first=False):
        is_terminated = False
        for i, node in enumerate(nodes):
            if is_terminated: break
            
            ntype = node[0]
            if ntype in ['statement', 'call', 'io', 'start', 'end']:
                self.add_block(ntype, node[1], skip_line=is_first)
                is_first = False
            
            elif ntype == 'while':
                cond = node[1]
                body_nodes = node[2]
                decision = self.add_block('while', cond, skip_line=is_first)
                is_first = False
                
                # 'Да' path
                decision_s = (decision.S[0], decision.S[1])
                self.d.add(flow.Line().at(decision_s).down(1.5).label('Да', loc='right', fontsize=75))
                self.last_pos = (decision_s[0], decision_s[1] - 1.5)
                self.render_nodes(body_nodes, nest + 1, is_first=True)
                
                # Loop back
                y_low = self.max_y - 2.0
                self.d.add(flow.Line().at(self.last_pos).toy(y_low))
                self.d.add(flow.Line().at((self.last_pos[0], y_low)).tox(decision.W[0] - 4.0))
                self.d.add(flow.Line().at((decision.W[0] - 4.0, y_low)).toy(decision.W[1]))
                self.d.add(flow.Line().at((decision.W[0] - 4.0, decision.W[1])).tox(decision.W[0]))
                
                # 'Нет' path
                self.last_pos = (decision.E[0], decision.E[1])
                self.d.add(flow.Line().at(self.last_pos).right(5.0).label('Нет', loc='top', fontsize=75))
                self.last_pos = (self.last_pos[0] + 5.0, self.last_pos[1])
                is_terminated = False # Continue after loop if needed (but usually main is while(true))

            elif ntype == 'if':
                cond = node[1]
                cons_nodes = node[2]
                alt_nodes = node[3]
                
                decision = self.add_block('if', cond, skip_line=is_first)
                is_first = False
                
                exit_y = 0 # To be determined
                
                # Да branch
                self.d.add(flow.Line().at(decision.S).down(1.5).label('Да', loc='right', fontsize=75))
                self.last_pos = (decision.S[0], decision.S[1] - 1.5)
                cons_term = self.render_nodes(cons_nodes, nest + 1, is_first=True)
                cons_exit = self.last_pos
                
                # Нет branch
                self.d.add(flow.Line().at(decision.E).right(4.0).label('Нет', loc='top', fontsize=75))
                self.last_pos = (decision.E[0] + 4.0, decision.E[1])
                alt_term = self.render_nodes(alt_nodes if alt_nodes else [], nest + 1, is_first=True)
                alt_exit = self.last_pos
                
                merge_y = self.max_y - 2.0
                if not cons_term:
                    self.d.add(flow.Line().at(cons_exit).toy(merge_y))
                    self.d.add(flow.Line().at((cons_exit[0], merge_y)).tox(self.axis_x))
                if not alt_term:
                    self.d.add(flow.Line().at(alt_exit).toy(merge_y))
                    self.d.add(flow.Line().at((alt_exit[0], merge_y)).tox(self.axis_x))
                
                self.last_pos = (self.axis_x, merge_y)
                self.max_y = min(self.max_y, merge_y)

            elif ntype == 'switch':
                cases = node[1]
                self.render_switch_comb(cases)
                is_first = False

            elif ntype == 'return':
                self.add_block('statement', node[1], skip_line=is_first)
                is_terminated = True

        return is_terminated

    def render_switch_comb(self, cases):
        # Anchor point
        start_y = self.max_y - 2.0
        case_spacing = 8.5 # Even tighter
        total_cases = len(cases)
        total_width = (total_cases - 1) * case_spacing
        start_x = self.axis_x - total_width / 2.0

        # Top Bus
        self.d.add(flow.Line().at(self.last_pos).toy(start_y))
        
        # Draw the full horizontal line
        self.d.add(flow.Line().at((start_x, start_y)).tox(start_x + total_width))

        exit_points = []
        deepest_y = start_y
        
        for i, case in enumerate(cases):
            case_label = case[0]
            case_nodes = case[1]
            cx = start_x + (i * case_spacing)
            
            # Drop line to case block
            self.d.add(flow.Line().at((cx, start_y)).toy(start_y - 1.5))
            
            # Case value label (e.g. "1")
            self.d.add(flow.Line().at((cx, start_y - 0.7)).length(0.01).label(case_label, loc='top', fontsize=75))
            
            # Backup state
            old_axis = self.axis_x
            old_max_y = self.max_y
            
            # Render case nodes on this vertical axis
            self.axis_x = cx
            self.last_pos = (cx, start_y - 1.5)
            # Reset max_y local to this branch to find its own end
            self.max_y = self.last_pos[1]
            
            self.render_nodes(case_nodes, is_first=True)
            exit_points.append(self.last_pos)
            deepest_y = min(deepest_y, self.max_y)
            
            # Restore
            self.axis_x = old_axis
            self.max_y = min(old_max_y, self.max_y)

        # Bottom Bus
        merge_y = deepest_y - 3.0
        # Draw collection line
        self.d.add(flow.Line().at((start_x, merge_y)).tox(start_x + total_width))
        
        for ep in exit_points:
            self.d.add(flow.Line().at(ep).toy(merge_y))
        
        # Center output from merge line
        self.last_pos = (self.axis_x, merge_y)
        self.max_y = min(self.max_y, merge_y)

    def save(self, filename):
        self.d.draw()
        self.d.save(filename)

def extract_main_data(node, code_bytes):
    # Specialized extraction for main and switch
    # (Similar to previous process_compound but keeps switch intact)
    functions = {}
    
    def walk(n):
        if n.type == 'function_definition':
            name_node = n.child_by_field_name('declarator')
            if name_node:
                # Sometimes it's nested (e.g. function_declarator)
                while name_node.child_by_field_name('declarator'):
                    name_node = name_node.child_by_field_name('declarator')
                
                name = code_bytes[name_node.start_byte:name_node.end_byte].decode('utf8')
                if 'main' in name:
                    body = n.child_by_field_name('body')
                    functions['main'] = [('start', 'Начало')] + process_main_compound(body, code_bytes) + [('end', 'Конец')]
        for child in n.children:
            walk(child)
            
    walk(node)
    return functions

def process_main_compound(node, code_bytes):
    extracted = []
    for child in node.children:
        if child.type == 'expression_statement':
            txt = code_bytes[child.start_byte:child.end_byte].decode('utf8').strip(';').strip()
            # Distinguish I/O
            if 'cin >>' in txt or 'cout <<' in txt:
                extracted.append(('io', txt))
            elif '(' in txt and ')' in txt:
                extracted.append(('call', txt))
            else:
                extracted.append(('statement', txt))
        
        elif child.type == 'declaration':
            txt = code_bytes[child.start_byte:child.end_byte].decode('utf8').strip(';').strip()
            if '=' in txt:
                extracted.append(('statement', txt))

        elif child.type == 'while_statement':
            cond_node = child.child_by_field_name('condition')
            cond = code_bytes[cond_node.start_byte:cond_node.end_byte].decode('utf8').strip('()').strip()
            body = child.child_by_field_name('body')
            extracted.append(('while', cond, process_main_compound(body, code_bytes)))

        elif child.type == 'if_statement':
            cond_node = child.child_by_field_name('condition')
            cond = code_bytes[cond_node.start_byte:cond_node.end_byte].decode('utf8').strip('()').strip()
            cons = child.child_by_field_name('consequent') # logic simplification
            alt = child.child_by_field_name('alternative')
            extracted.append(('if', cond, process_main_compound(cons, code_bytes) if cons else [], 
                             process_main_compound(alt, code_bytes) if alt else []))

        elif child.type == 'switch_statement':
            # Extract case blocks
            body = child.child_by_field_name('body')
            cases = []
            for bchild in body.children:
                if bchild.type == 'case_statement':
                    val_node = bchild.child_by_field_name('value')
                    val = code_bytes[val_node.start_byte:val_node.end_byte].decode('utf8') if val_node else ""
                    case_body = []
                    for sub in bchild.children:
                        if sub.type not in [':', 'case', 'value']:
                            case_body.extend(process_main_compound(sub, code_bytes))
                    cases.append((val, case_body))
                elif bchild.type == 'default_statement':
                    case_body = []
                    for sub in bchild.children:
                        if sub.type not in [':', 'default']:
                            case_body.extend(process_main_compound(sub, code_bytes))
                    cases.append(('default', case_body))
            extracted.append(('switch', cases))
            
        elif child.type == 'return_statement':
            txt = code_bytes[child.start_byte:child.end_byte].decode('utf8').strip(';').strip()
            extracted.append(('return', txt))

        elif child.type == 'compound_statement':
            extracted.extend(process_main_compound(child, code_bytes))

    return extracted

def main():
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    with open(input_file, 'r', encoding='utf-8') as f:
        code = f.read()

    parser = get_cpp_parser()
    tree = parser.parse(bytes(code, 'utf8'))
    functions = extract_main_data(tree.root_node, bytes(code, 'utf8'))
    
    if 'main' in functions:
        renderer = SpecializedMainRenderer()
        renderer.render_nodes(functions['main'])
        renderer.save(output_file)
        print(f"Saved {output_file}")

if __name__ == "__main__":
    main()

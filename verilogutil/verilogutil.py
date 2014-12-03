# Class/function to process verilog file
import re, string, os

# regular expression for signal/variable declaration:
#   start of line follow by 1 to 4 word,
#   an optionnal array size,
#   an optional list of words
#   the signal itself (not part of the regular expression)
re_decl  = r'(?<!@)\s*(?:^|,|\()\s*(\w+\s+)?(\w+\s+)?(\w+\s+)?([A-Za-z_][\w\:\.]*\s+)(\[[\w\:\-`\s]+\])?\s*([A-Za-z_][\w=,\s]*,\s*)?\b'
re_enum  = r'^\s*(typedef\s+)?(enum)\s+(\w+\s*)?(\[[\w\:\-`\s]+\])?\s*(\{[\w=,\s`\']+\})\s*([A-Za-z_][\w=,\s]*,\s*)?\b'
re_union = r'^\s*(typedef\s+)?(struct|union)\s+(packed)?(signed|unsigned)?\s*(\{[\w,;\s`\[\:\]]+\})\s*([A-Za-z_][\w=,\s]*,\s*)?\b'
re_inst  = r'^\s*()()()(\w+)\s*(#\s*\([^;]+\))?\s*()\b'

# TODO: create a class to handle the cache for N module
cache_module = {'mname' : '', 'fname' : '', 'date' : 0, 'info' : None}

def clean_comment(txt):
    txt_nc = txt
    #remove multiline comment
    txt_nc = re.sub(r"(?s)/\*.*?\*/","",txt_nc)
    #remove singleline comment
    txt_nc = re.sub(r"//.*?$","",txt_nc, flags=re.MULTILINE)
    return txt_nc

# Extract the declaration of var_name from txt
#return a tuple: complete string, type, arraytype (none, fixed, dynamic, queue, associative)
def get_type_info(txt,var_name):
    txt = clean_comment(txt)
    m = re.search(re_decl+r'('+var_name+r'\b(\[.*?\]\s*)?)[^\.]*$', txt, flags=re.MULTILINE)
    idx_type = 3
    idx_bw = 4
    idx_max = 5
    tag = 'decl'
    # print("get_type_info for var " + str(var_name) + " in \n" + str(txt))
    #if regex on signal/variable declaration failed, try looking for an enum, struct or a typedef enum/struct
    if m is None:
        m = re.search(re_inst+r'('+var_name+r')\b.*$', txt, flags=re.MULTILINE)
        tag = 'inst'
        if not m :
            m = re.search(re_enum+r'('+var_name+r')\b.*$', txt, flags=re.MULTILINE)
            tag = 'enum'
            if m is None:
                m = re.search(re_union+r'('+var_name+r')\b.*$', txt, flags=re.MULTILINE)
                tag = 'struct'
            idx_type = 1
            idx_bw = 3
    return get_type_info_from_match(var_name,m,idx_type,idx_bw,idx_max,tag)[0]

# Extract all signal declaration
def get_all_type_info(txt):
    # txt = clean_comment(txt)
    # Suppose text has already been cleaned
    ti = []
    idx_type = 3
    idx_bw = 4
    idx_max = 5
    # Look for signal declaration
    # print('Look for signal declaration')
    r = re.compile(re_decl+r'(\w+(\[.*?\]\s*)?)\b\s*(;|,|\)\s*;)',flags=re.MULTILINE)
    for m in r.finditer(txt):
        ti += get_type_info_from_match('',m,idx_type,idx_bw,idx_max,'decl')
    # Look for interface instantiation
    # print('Look for interface instantiation')
    r = re.compile(re_inst+r'(\w+)\b\s*\(',flags=re.MULTILINE)
    for m in r.finditer(txt):
        ti += get_type_info_from_match('',m,idx_type,idx_bw,idx_max,'inst')
    # Look for enum declaration
    # print('Look for enum declaration')
    idx_type = 1
    idx_bw = 3
    r = re.compile(re_enum+r'(\w+)\b\s*;',flags=re.MULTILINE)
    for m in r.finditer(txt):
        ti += get_type_info_from_match('',m,idx_type,idx_bw,idx_max,'enum')
    # Look for struct declaration
    # print('Look for struct declaration')
    r = re.compile(re_union+r'(\w+)\b\s*;',flags=re.MULTILINE)
    for m in r.finditer(txt):
        ti += get_type_info_from_match('',m,idx_type,idx_bw,idx_max,'struct')
    # print(ti)
    return ti

# Get type info from a match object
def get_type_info_from_match(var_name,m,idx_type,idx_bw,idx_max,tag):
    #return a tuple of None if not found
    if m is None:
        return [{'decl':None,'type':None,'array':"None",'bw':"None", 'name':var_name, 'tag':tag}]
    line = m.group(0).strip()
    # Extract the type itself: should be the mandatory word, except if is a sign qualifier
    t = str.rstrip(m.groups()[idx_type]).split('.')[0]
    if t=="unsigned" or t=="signed": # TODO check if other cases might happen
        if m.groups()[2] is not None:
            t = str.rstrip(m.groups()[2]) + ' ' + t
        elif m.groups()[1] is not None:
            t = str.rstrip(m.groups()[1]) + ' ' + t
        elif m.groups()[0] is not None:
            t = str.rstrip(m.groups()[0]) + ' ' + t
    elif t=="const": # identifying a variable as simply const is typical of a struct/union : look for it
        m = re.search( re_union+var_name+r'.*$', txt, flags=re.MULTILINE)
        if m is None:
            return {'decl':None,'type':None,'array':"None",'bw':"None", 'name':var_name, 'tag':tag}
        t = m.groups()[1]
        idx_bw = 3
    # print("[get_type_info] type => " + str(t))
    ft = ''
    bw = 'None'
    #Concat the first 5 word if not None (basically all signal declaration until signal list)
    for i in range(0,idx_max):
        if m.groups()[i] is not None:
            tmp = m.groups()[i].strip()
            # Cleanup space in enum/struct declaration
            if i==4 and t in ['enum','struct']:
                tmp = re.sub(r'\s+',' ',tmp,flags=re.MULTILINE)
            #Cleanup spaces in bitwidth
            if i==idx_bw:
                tmp = re.sub(r'\s+','',tmp,flags=re.MULTILINE)
                bw = tmp
            # regex can catch more than wanted, so filter based on a list
            if tmp not in ['end']:
                ft += tmp + ' '
    if var_name!='':
        signal_list = re.findall(r'('+var_name + r')\b\s*(\[(.*?)\]\s*)?', m.groups()[idx_max+1], flags=re.MULTILINE)
    else:
        signal_list = []
        if m.groups()[idx_max]:
            signal_list = re.findall(r'(\w+)\s*(\[.*?\]\s*,)?', m.groups()[idx_max], flags=re.MULTILINE)
        signal_list += re.findall(r'(\w+)\s*(\[.*?\]\s*,)?', m.groups()[idx_max+1], flags=re.MULTILINE)
    # remove reserved keyword that could end up in the list
    signal_list = [s for s in signal_list if s[0] not in ['if','case', 'for', 'foreach', 'generate']]
    # print("[get_type_info] signal_list = " + str(signal_list) + ' for line ' + line)
    ti = []
    for signal in signal_list :
        ft += signal[0]
        # print("get_type_info: decl => " + ft)
        # Check if the variable is an array and the type of array (fixed, dynamic, queue, associative)
        at = "None"
        if signal[1]!='':
            ft += '[' + signal[2] + ']'
            if signal[2] =="":
                at='dynamic'
            elif signal[2]=='$':
                at='queue'
            elif signal[2]=='*':
                at='associative'
            else:
                ma= re.search(r'[A-Za-z_][\w]*',signal[2])
                if ma:
                    at='associative'
                else:
                    at='fixed'
        # print("Array: " + str(m) + "=>" + str(at))
        ti.append({'decl':ft,'type':t,'array':at,'bw':bw, 'name':signal[0], 'tag':tag})
    return ti


# Parse a module for port information
def parse_module_file(fname,mname=r'\w+'):
    # print("Parsing file " + fname + " for module " + mname)
    fdate = os.path.getmtime(fname)
    # Check Cache module
    if cache_module['mname'] == mname and cache_module['fname'] == fname and cache_module['date']==fdate:
        # print('Using cache !')
        return cache_module['info']
    #
    flines = ''
    with open(fname, "r") as f:
        flines = str(f.read())
    flines = clean_comment(flines)
    minfo = parse_module(flines,mname)
    # Put information in cache:
    cache_module['info']  = minfo
    cache_module['mname'] = mname
    cache_module['fname'] = fname
    cache_module['date']  = fdate
    return minfo

def parse_module(flines,mname):
    # print("Parsing for module " + mname + ' in \n' + flines)
    m = re.search(r"(?s)(?P<type>module|interface)\s+(?P<name>"+mname+")\s*(?P<param>#\s*\([^;]+\))?\s*\((?P<content>.+?)\)\s*;.*?(?P<ending>endmodule|endinterface)", flines, re.MULTILINE)
    if m is None:
        return None
    mname = m.group('name')
    # Extract parameter name
    params = None
    ## Parameter define in ANSI style
    if m.group('param'):
        s = clean_comment(m.groups()[1])
        r = re.compile(r"(?P<name>\w+)\s*=\s*(?P<value>[\w\-\+`]+)")
        params = [m.groupdict() for m in r.finditer(s)]
    ##TODO: look for parameter not define in the module declaration (optionnaly?)
    # Extract all type information inside the module : signal/port declaration, interface/module instantiation
    ati = get_all_type_info(m.group(0))
    # Extract port name
    ports = None
    if m.group('content') is not None:
        s = clean_comment(m.group('content'))
        ports_name = re.findall(r"(\w+)\s*(?=,|$)",s)
        # get type for each port
        ports = []
        ports = [ti for ti in ati if ti['name'] in ports_name]
    # Extract instances name
    inst = [ti for ti in ati if ti['type']!='module' and ti['tag']=='inst']
    minfo = {'name': mname, 'param':params, 'port':ports, 'inst':inst, 'type':m.group('type')}
    # print (minfo)
    return minfo

# Fill all entry of a case for enum or vector (limited to 8b)
# ti is the type infor return by get_type_info
def fill_case(ti):
    if not ti['type']:
        return None
    t = ti['type'].split()[0]
    s = '\n'
    if t == 'enum':
        # extract enum from the declaration
        m = re.search(r'\{(.*)\}', ti['decl'])
        if m :
            el = re.findall(r"(\w+).*?(,|$)",m.groups()[0])
            maxlen = max([len(x[0]) for x in el])
            if maxlen < 7:
                maxlen = 7
            for x in el:
                s += '\t' + x[0].ljust(maxlen) + ' : ;\n'
            s += '\tdefault'.ljust(maxlen+1) + ' : ;\nendcase'
            return (s,[x[0] for x in el])
    elif t in ['logic','bit','reg','wire']:
        m = re.search(r'\[\s*(\d+)\s*\:\s*(\d+)',ti['bw'])
        if m :
            bw = int(m.groups()[0]) + 1 - int(m.groups()[1])
            if bw <=8 :
                for i in range(0,(1<<bw)):
                    s += '\t' + str(i).ljust(7) + ' : ;\n'
                s += '\tdefault : ;\nendcase'
                return (s,range(0,(1<<bw)))
    return None


import json
pre=json.load(open('phase_eval_direct_phase3_pre_p3_1775596059.json',encoding='utf-8'))
post=json.load(open('phase_eval_direct_phase3_post_p3b_1775596354.json',encoding='utf-8'))
print('PHASE3 CHANGES')
changed=reg_nf=imp_nf=0
for a,b in zip(pre['results'],post['results']):
    if a['answer']!=b['answer'] or a['not_found']!=b['not_found']:
        changed+=1
        if (not a['not_found']) and b['not_found']:
            reg_nf+=1
        if a['not_found'] and (not b['not_found']):
            imp_nf+=1
        print('-',a['query'])
        print('  pre:',a['answer'])
        print('  post:',b['answer'])
print(f'summary changed={changed} reg_nf={reg_nf} imp_nf={imp_nf}')

pre_g=json.load(open('phase_eval_direct_global_pre_p3_1775596088.json',encoding='utf-8'))
post_g=json.load(open('phase_eval_direct_global_post_p3b_1775596383.json',encoding='utf-8'))
print('GLOBAL CHANGES')
changed=reg_nf=imp_nf=0
for a,b in zip(pre_g['results'],post_g['results']):
    if a['answer']!=b['answer'] or a['not_found']!=b['not_found']:
        changed+=1
        if (not a['not_found']) and b['not_found']:
            reg_nf+=1
        if a['not_found'] and (not b['not_found']):
            imp_nf+=1
        print('-',a['query'])
        print('  pre:',a['answer'])
        print('  post:',b['answer'])
print(f'summary changed={changed} reg_nf={reg_nf} imp_nf={imp_nf}')

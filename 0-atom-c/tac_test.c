/*
 * tac_test.c — Ever / Tapestry, Three-Address IR verification
 *
 * Tests opcodes, lowering, all three optimisation passes,
 * confidence propagation, and the TAC interpreter.
 */
#include <stdio.h>
#include <string.h>
#include <math.h>
#include "tac.h"
#ifndef E_INTAKE
#define E_INTAKE 120
#endif

static int ok_n=0, fail_n=0;
static void _ok(const char *n, int c){
    if(c){ok_n++;printf("  \u2713 %s\n",n);}
    else {fail_n++;printf("  \u2717 %s\n",n);}
}
#define ok(n,c) _ok(n,c)

int main(void){
    printf("\n=== Ever \u2014 Three-Address IR (EvTAC) ===\n\n");

    /* ── Opcodes ── */
    printf("Opcode metadata\n");
    ok("CONST name",    strcmp(ev_opcode_name(OP_CONST),"CONST")==0);
    ok("ADD is binary", ev_opcode_is_binary(OP_ADD));
    ok("LTE is cmp",    ev_opcode_is_cmp(OP_LTE));
    ok("JUMP is branch",ev_opcode_is_branch(OP_JUMP));
    ok("RETURN branch", ev_opcode_is_branch(OP_RETURN));
    ok("CONST not binop",!ev_opcode_is_binary(OP_CONST));

    /* ── Virtual registers ── */
    printf("\nVirtual registers\n");
    EvReg rv = ev_reg_void();
    ok("void id=0",       rv.id == EV_REG_VOID);
    ok("void is_void",    ev_reg_is_void(rv));
    EvArena *a = ev_arena_new("tac-test");
    EvReg r1 = ev_reg_temp(1,EV_INT,E_CERTAIN);
    ok("temp id=1",       r1.id == 1);
    ok("temp type INT",   r1.type == EV_INT);
    ok("temp conf=256",   r1.confidence == E_CERTAIN);
    EvReg rn = ev_reg_named(2,"x",EV_REAL,200,a);
    ok("named id=2",      rn.id == 2);
    ok("named name=x",    rn.name && strcmp(rn.name,"x")==0);
    ok("named conf=200",  rn.confidence == 200);

    /* ── Builder + emit ── */
    printf("\nBuilder and emit\n");
    EvModule *m  = ev_module_new("test",a);
    const char *ps[] = {"n"};
    EvFunc   *f  = ev_module_add_func(m,"sq",ps,1);
    EvBlock  *b0 = ev_func_new_block(f);
    EvBuilder bld = ev_builder(m,f,b0);

    /* sq(n) = n * n  →  t0=LOAD n; t1=LOAD n; t2=MUL t0,t1; RETURN t2 */
    EvReg tload0 = ev_emit_load(&bld,"n",EV_INT,E_CERTAIN,1);
    EvReg tload1 = ev_emit_load(&bld,"n",EV_INT,E_CERTAIN,1);
    EvReg tmul   = ev_emit_binop(&bld,OP_MUL,tload0,tload1,1);
    ev_emit_return(&bld,tmul,1);

    ok("4 instrs in block",   b0->len == 4);
    ok("LOAD op",             b0->instrs[0].op == OP_LOAD);
    ok("MUL op",              b0->instrs[2].op == OP_MUL);
    ok("RETURN op",           b0->instrs[3].op == OP_RETURN);
    ok("MUL dest is temp",    !ev_reg_is_void(b0->instrs[2].dest));
    ok("MUL src0 links",      b0->instrs[2].src0.id == tload0.id);
    ok("MUL src1 links",      b0->instrs[2].src1.id == tload1.id);
    ok("MUL type INT",        tmul.type == EV_INT);

    /* emit a CONST and verify confidence */
    EvBlock *b1 = ev_func_new_block(f);
    ev_builder_switch_block(&bld, b1);
    EvReg rc = ev_emit_const(&bld, ev_int(42), 1);
    ok("CONST conf=Certain",  rc.confidence == E_CERTAIN);
    ok("CONST type INT",      rc.type == EV_INT);

    /* JUMP_IF sets block successors */
    EvBlock *b2 = ev_func_new_block(f);
    EvBlock *b3 = ev_func_new_block(f);
    ev_builder_switch_block(&bld, b2);
    EvReg cond_r = ev_emit_const(&bld, ev_bool(1), 1);
    ev_emit_jump_if(&bld, cond_r, b3->id, b0->id, 1);
    ok("JUMP_IF nsucc=2",     b2->nsucc == 2);
    ok("JUMP_IF true=b3",     b2->succ[0] == b3->id);
    ok("JUMP_IF false=b0",    b2->succ[1] == b0->id);

    /* ── Lowering: EvNode → TAC ── */
    printf("\nLowering: EvNode \u2192 TAC\n");
    EvArena *la = ev_arena_new("lower");
    EvModule *lm = ev_module_new("lower",la);

    /* 6 + 36 */
    EvNode *n6   = ev_node_int(la,6,1);
    EvNode *n36  = ev_node_int(la,36,1);
    EvNode *nadd = ev_node_binop(la,EV_NODE_ADD,n6,n36,1);
    EvModule *am = ev_lower_module("add-test",nadd,la);
    ok("add module created",  am != NULL);
    ok("global body has blk", am->global_body->nblocks > 0);
    EvBlock *gb = am->global_body->blocks[0];
    ok("CONST 6 emitted",     gb->instrs[0].op == OP_CONST
                              && gb->instrs[0].literal.body.as_int == 6);
    ok("CONST 36 emitted",    gb->instrs[1].op == OP_CONST
                              && gb->instrs[1].literal.body.as_int == 36);
    ok("ADD emitted",         gb->instrs[2].op == OP_ADD);

    /* def fact(n) = if n <= 1 then 1 else n * fact(n-1) */
    const char *pn[] = {"n"};
    EvNode *vn  = ev_node_var(la,"n",1);
    EvNode *one = ev_node_int(la,1,1);
    EvNode *cmp = ev_node_binop(la,EV_NODE_LTE,vn,one,1);
    EvNode *one2= ev_node_int(la,1,1);
    EvNode *vn2 = ev_node_var(la,"n",1);
    EvNode *vn3 = ev_node_var(la,"n",1);
    EvNode *sub = ev_node_binop(la,EV_NODE_SUB,vn3,ev_node_int(la,1,1),1);
    EvNode *rc2 = ev_node_call(la,"fact",(EvNode*[]){sub},1,1);
    EvNode *mul = ev_node_binop(la,EV_NODE_MUL,vn2,rc2,1);
    EvNode *iff = ev_node_if(la,cmp,one2,mul,1);
    EvNode *fn  = ev_node_def(la,"fact",pn,1,iff,1);

    EvArena *fa2 = ev_arena_new("fact");
    EvModule *fm  = ev_module_new("fact",fa2);
    EvFunc   *ff  = ev_lower_func(fm,fn);
    ok("fact func lowered",   ff != NULL);
    ok("fact nblocks >= 4",   ff && ff->nblocks >= 4);
    ok("fact has regs",       ff && ff->reg_counter > 1);
    ok("fact in module",      fm->nfuncs == 1);
    ok("fact name",           ff && strcmp(ff->name,"fact")==0);

    /* check that blocks contain expected opcodes */
    int has_load=0, has_lte=0, has_jump_if=0, has_call=0, has_ret=0;
    for(int32_t bi=0;bi<ff->nblocks;bi++){
        EvBlock *blk=ff->blocks[bi];
        for(int32_t ii=0;ii<blk->len;ii++){
            EvOpcode op=blk->instrs[ii].op;
            if(op==OP_LOAD)    has_load=1;
            if(op==OP_LTE)     has_lte=1;
            if(op==OP_JUMP_IF) has_jump_if=1;
            if(op==OP_CALL)    has_call=1;
            if(op==OP_RETURN)  has_ret=1;
        }
    }
    ok("LOAD in fact",    has_load);
    ok("LTE in fact",     has_lte);
    ok("JUMP_IF in fact", has_jump_if);
    ok("CALL in fact",    has_call);
    ok("RETURN in fact",  has_ret);

    /* ── Optimisation pass 1: constant folding ── */
    printf("\nPass 1 — constant folding\n");
    EvArena *ca = ev_arena_new("cfold");
    EvModule *cm = ev_module_new("cfold",ca);
    const char *nop[] = {};
    EvFunc *cf = ev_module_add_func(cm,"cf",nop,0);
    EvBlock *cb = ev_func_new_block(cf);
    EvBuilder cb_bld = ev_builder(cm,cf,cb);
    /* emit 3 - 1 as constants */
    EvReg r3 = ev_emit_const(&cb_bld,ev_int(3),1);
    EvReg r1_ = ev_emit_const(&cb_bld,ev_int(1),1);
    EvReg rsub = ev_emit_binop(&cb_bld,OP_SUB,r3,r1_,1);
    ok("before fold: SUB op", cb->instrs[2].op == OP_SUB);
    int changes = ev_pass_const_fold(cf);
    ok("fold reports change",  changes > 0);
    ok("after fold: CONST op", cb->instrs[2].op == OP_CONST);
    ok("folded value = 2",     cb->instrs[2].literal.body.as_int == 2);

    /* fold a comparison: 5 > 3 → true */
    EvReg r5 = ev_emit_const(&cb_bld,ev_int(5),1);
    EvReg r3b= ev_emit_const(&cb_bld,ev_int(3),1);
    EvReg rgt= ev_emit_binop(&cb_bld,OP_GT,r5,r3b,1);
    ev_pass_const_fold(cf);
    /* find the GT instr and check it folded */
    int found_gt_fold=0;
    for(int i=0;i<cb->len;i++)
        if(cb->instrs[i].dest.id==rgt.id && cb->instrs[i].op==OP_CONST
           && cb->instrs[i].literal.body.as_bool==1)
            found_gt_fold=1;
    ok("5 > 3 folded to true", found_gt_fold);
    (void)rsub;

    /* ── Optimisation pass 2: dead-register elimination ── */
    printf("\nPass 2 — dead-register elimination\n");
    EvArena *da2 = ev_arena_new("dead");
    EvModule *dm = ev_module_new("dead",da2);
    EvFunc *df = ev_module_add_func(dm,"df",nop,0);
    EvBlock *db = ev_func_new_block(df);
    EvBuilder db_bld = ev_builder(dm,df,db);
    EvReg d1 = ev_emit_const(&db_bld,ev_int(10),1);  /* will be used */
    EvReg d2 = ev_emit_const(&db_bld,ev_int(99),1);  /* dead — never read */
    EvReg d3 = ev_emit_const(&db_bld,ev_int(2),1);   /* will be used */
    EvReg dmul = ev_emit_binop(&db_bld,OP_MUL,d1,d3,1);
    ev_emit_return(&db_bld,dmul,1);
    int dead_ch = ev_pass_dead_regs(df);
    ok("dead pass finds d2", dead_ch > 0);
    int d2_nop=0;
    for(int i=0;i<db->len;i++)
        if(db->instrs[i].dest.id==d2.id && db->instrs[i].op==OP_NOP)
            d2_nop=1;
    ok("d2 replaced with NOP", d2_nop);
    int d1_alive=0;
    for(int i=0;i<db->len;i++)
        if(db->instrs[i].dest.id==d1.id && db->instrs[i].op==OP_CONST)
            d1_alive=1;
    ok("d1 still CONST",       d1_alive);

    /* ── Optimisation pass 3: confidence propagation ── */
    printf("\nPass 3 — confidence propagation\n");
    EvArena *pa2 = ev_arena_new("conf");
    EvModule *pm = ev_module_new("conf",pa2);
    EvFunc *pf = ev_module_add_func(pm,"pf",nop,0);
    EvBlock *pb = ev_func_new_block(pf);
    EvBuilder pb_bld = ev_builder(pm,pf,pb);

    /* CONST gets E_CERTAIN; LOAD gets E_INTAKE (120) */
    EvReg pc1  = ev_emit_const(&pb_bld,ev_int(42),1);
    EvReg pld  = ev_emit_load(&pb_bld,"x",EV_INT,E_INTAKE,1);
    EvReg padd = ev_emit_binop(&pb_bld,OP_ADD,pc1,pld,1);
    ev_pass_conf_prop(pf);

    ok("CONST conf=Certain", pc1.confidence == E_CERTAIN);
    /* after propagation, ADD dest confidence = min(certain, intake) = 120 */
    int padd_conf=0;
    for(int i=0;i<pb->len;i++)
        if(pb->instrs[i].dest.id==padd.id)
            padd_conf=pb->instrs[i].dest.confidence;
    ok("ADD conf = min(256,120) = 120", padd_conf <= 120);

    /* ── TAC interpreter: 6 + 36 = 42 ── */
    printf("\nTAC interpreter\n");
    EvArena *ia = ev_arena_new("interp");
    EvNode *iadd = ev_node_binop(ia,EV_NODE_ADD,
                                 ev_node_int(ia,6,1),
                                 ev_node_int(ia,36,1),1);
    EvModule *im = ev_lower_module("interp",iadd,ia);
    ev_optimise(im->global_body);
    EvInterp *ip = ev_interp_new(im);
    EValue result = ev_interp_run(ip);
    ok("6+36 result tag INT",  result.tag == EV_INT);
    ok("6+36 = 42",            result.body.as_int == 42);

    /* n * n where n=7 */
    EvArena *sa = ev_arena_new("sq");
    EvNode *sqn  = ev_node_var(sa,"n",1);
    EvNode *sqn2 = ev_node_var(sa,"n",1);
    EvNode *sqmul= ev_node_binop(sa,EV_NODE_MUL,sqn,sqn2,1);
    EvNode *sqfn = ev_node_def(sa,"square",pn,1,sqmul,1);
    EvModule *sm  = ev_lower_module("sq",sqfn,sa);
    ev_optimise(sm->funcs[0]);
    EvInterp *sip = ev_interp_new(sm);
    EValue sarg = ev_int(7);
    EValue sq7 = ev_interp_call(sip,"square",&sarg,1);
    ok("square(7) = 49",       sq7.tag==EV_INT && sq7.body.as_int==49);
    ev_interp_free(sip);

    /* if 10 > 5 then 42 else 0 */
    EvArena *ia2 = ev_arena_new("if");
    EvNode *i10 = ev_node_int(ia2,10,1);
    EvNode *i5  = ev_node_int(ia2,5,1);
    EvNode *igt = ev_node_binop(ia2,EV_NODE_GT,i10,i5,1);
    EvNode *i42 = ev_node_int(ia2,42,1);
    EvNode *i0  = ev_node_int(ia2,0,1);
    EvNode *iiff= ev_node_if(ia2,igt,i42,i0,1);
    EvModule *im2 = ev_lower_module("if",iiff,ia2);
    EvInterp *ip2 = ev_interp_new(im2);
    EValue if_res = ev_interp_run(ip2);
    ok("if 10>5 then 42",      if_res.tag==EV_INT && if_res.body.as_int==42);
    ev_interp_free(ip2);

    /* ── Print a function ── */
    printf("\nPretty-print (6+36):\n");
    ev_print_module(im);

    ev_interp_free(ip);
    ev_module_free(am); ev_module_free(fm); ev_module_free(cm);
    ev_module_free(dm); ev_module_free(pm); ev_module_free(sm);
    ev_module_free(im); ev_module_free(im2); ev_module_free(lm);

    printf("\n=== EvTAC: %d passed, %d failed ===\n\n", ok_n, fail_n);
    return fail_n==0 ? 0 : 1;
}

/*
 * tac_test.c — Ever / Tapestry, Three-Address IR verification
 *
 * Tests opcodes, lowering, all three optimisation passes,
 * confidence propagation, and the TAC interpreter.
 */
#include <stdio.h>
#include <stdlib.h>
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

/* Lower an EvNode program through ev_lower_module and run it on the real
   path. *lowered reports whether lowering accepted the program. */
static EValue run_node(EvArena *a, EvNode *n, int optimise, int *lowered) {
    EvModule *m = ev_lower_module("t", n);
    if (lowered) *lowered = (m != NULL);
    if (!m) return ev_void();
    if (optimise) ev_optimise(m->global_body);
    EvInterp *ip = ev_interp_new(m);
    EValue r = ev_interp_run(ip);
    ev_interp_free(ip);
    ev_module_free(m);
    return r;
}

static EvNode *heal_node(EvArena *a, EvNode *primary, EvNode *fallback) {
    EvNode *h = ev_node_new(a, EV_NODE_HEAL, 1);
    ev_node_add_child(h, primary);
    ev_node_add_child(h, ev_node_text(a, "strategy", 1));
    ev_node_add_child(h, fallback);
    return h;
}

/* heal with a chosen strategy text, for the strategy tests */
static EvNode *heal_with(EvArena *a, EvNode *primary, const char *strat, EvNode *fallback) {
    EvNode *h = ev_node_new(a, EV_NODE_HEAL, 1);
    ev_node_add_child(h, primary);
    ev_node_add_child(h, ev_node_text(a, strat, 1));
    ev_node_add_child(h, fallback);
    return h;
}

/* append a repair to an in-memory registry; strat NULL makes a wildcard */
static void add_test_repair(EvRepairRegistry *reg, const char *fail, const char *fix,
                            int32_t kind, const char *strat) {
    EvRepair *r = (EvRepair*)calloc(1, sizeof *r);
    r->failure_text = strdup(fail);
    r->fixture_text = strdup(fix);
    r->kind = kind;
    r->strategy = strat ? strdup(strat) : NULL;
    reg->repairs[reg->count++] = r;
}

static EvNode *sum_node(EvArena *a, EvNode *l, EvNode *r) {
    return ev_node_binop(a, EV_NODE_ADD, l, r, 1);
}

static EvNode *if_term(EvArena *a) {
    return ev_node_if(a, ev_node_bool(a, 1, 1), ev_node_int(a, 1, 1),
                      ev_node_int(a, 0, 1), 1);
}

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
    ev_emit_jump_if(&bld, cond_r, b3->id, b0->id, b3->id, 1);
    ok("JUMP_IF nsucc=2",     b2->nsucc == 2);
    ok("JUMP_IF true=b3",     b2->succ[0] == b3->id);
    ok("JUMP_IF false=b0",    b2->succ[1] == b0->id);
    ok("JUMP_IF unknown=b3",  b2->instrs[b2->len-1].unknown_label == b3->id);

    /* ── Lowering: EvNode → TAC ── */
    printf("\nLowering: EvNode \u2192 TAC\n");
    EvArena *la = ev_arena_new("lower");
    EvModule *lm = ev_module_new("lower",la);

    /* 6 + 36 */
    EvNode *n6   = ev_node_int(la,6,1);
    EvNode *n36  = ev_node_int(la,36,1);
    EvNode *nadd = ev_node_binop(la,EV_NODE_ADD,n6,n36,1);
    EvModule *am = ev_lower_module("add-test",nadd);
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
    const char *nop[1] = { NULL };
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
    EvModule *im = ev_lower_module("interp",iadd);
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
    EvModule *sm  = ev_lower_module("sq",sqfn);
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
    EvModule *im2 = ev_lower_module("if",iiff);
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


    /* ── HEAL on the real path ── */
    printf("\nHEAL\n");
    {
        int lw = 0;
        g_repair_registry = ev_repair_registry_new("7-refix-node/repairs.jsonl");
        EvArena *ha = ev_arena_new("heal-test");


        EValue r1 = run_node(ha, heal_node(ha, ev_node_int(ha, 10, 1),
                                           ev_node_int(ha, 1, 1)), 0, &lw);
        ok("heal(10) lowers",                    lw);
        ok("heal(10) takes the primary (10)",    r1.tag == EV_INT && r1.body.as_int == 10);

        EValue r2 = run_node(ha, heal_node(ha, ev_node_var(ha, "x_undef", 1),
                                           ev_node_int(ha, 42, 1)), 0, &lw);
        ok("heal(z) takes the fallback (42)",    r2.tag == EV_INT && r2.body.as_int == 42);

        /* test recovery from archived repair: fallback is 99 so a pass can
           only come from the registry's fixture "1", not from the fallback */
        EValue r_rec = run_node(ha, heal_node(ha, ev_node_binop(ha, EV_NODE_DIV, ev_node_int(ha, 1, 1),
                                                                ev_node_int(ha, 0, 1), 1),
                                              ev_node_int(ha, 99, 1)), 0, &lw);
        ok("heal(1/0) recovers to 1 (not fallback 99)", r_rec.tag == EV_INT && r_rec.body.as_int == 1);

        EValue r3 = run_node(ha, heal_node(ha, ev_node_var(ha, "x_undef", 1),
                                           sum_node(ha, ev_node_int(ha, 2, 1),
                                                    ev_node_int(ha, 3, 1))), 1, &lw);
        ok("heal(z) fallback 2+3 optimised -> 5", r3.tag == EV_INT && r3.body.as_int == 5);

        EValue r4 = run_node(ha, heal_node(ha, ev_node_int(ha, 10, 1),
                                           sum_node(ha, ev_node_int(ha, 2, 1),
                                                    ev_node_int(ha, 3, 1))), 1, &lw);
        ok("heal(10) fallback 2+3 optimised -> 10", r4.tag == EV_INT && r4.body.as_int == 10);

        /* the fallback is lowered only on the repair path */
        EvModule *lm = ev_lower_module("lazy", heal_node(ha, ev_node_int(ha, 10, 1),
                                        ev_node_var(ha, "fb_undef", 1)));
        int heal_in_entry = 0, fb_in_entry = 0;
        if (lm) {
            EvBlock *eb = lm->global_body->blocks[0];
            for (int32_t i = 0; i < eb->len; i++) {
                if (eb->instrs[i].op == OP_HEAL) heal_in_entry = 1;
                if (eb->instrs[i].op == OP_LOAD && eb->instrs[i].name &&
                        strcmp(eb->instrs[i].name, "fb_undef") == 0)
                    fb_in_entry = 1;
            }
            ev_module_free(lm);
        }
        ok("heal ends the entry block",          heal_in_entry);
        ok("fallback not lowered on trusted path", !fb_in_entry);

        /* the merged result is no more certain than its weaker arm */
        EvModule *cm = ev_lower_module("conf", heal_node(ha, ev_node_var(ha, "x_undef", 1),
                                        ev_node_int(ha, 42, 1)));
        int16_t mconf = -1;
        if (cm) {
            EvBlock *mb = NULL;
            for (int32_t bi = 0; bi < cm->global_body->nblocks; bi++) {
                EvBlock *b = cm->global_body->blocks[bi];
                for (int32_t ii = 0; ii < b->len; ii++) {
                    if (b->instrs[ii].op == OP_LOAD) {
                        mb = b;
                        break;
                    }
                }
                if (mb) break;
            }
            if (mb) {
                for (int32_t i = 0; i < mb->len; i++)
                    if (mb->instrs[i].op == OP_LOAD) mconf = mb->instrs[i].dest.confidence;
            }
            ev_module_free(cm);
        }
        ok("heal result takes the lower arm confidence", mconf == E_INTAKE);
        ev_arena_free(ha);
    }

    /* ── IF on unknown and non-bool conditions ── */
    printf("\nIF conditions\n");
    {
        int lw = 0;
        EvArena *ia = ev_arena_new("if-test");
        EValue z1 = run_node(ia, ev_node_if(ia, ev_node_var(ia, "x_undef", 1),
                                            ev_node_int(ia, 1, 1), ev_node_int(ia, 2, 1), 1), 0, &lw);
        ok("if (z) is z, not an arm",            lw && z1.tag == EV_VOID);
        EValue t5 = run_node(ia, ev_node_if(ia, ev_node_int(ia, 5, 1),
                                            ev_node_int(ia, 1, 1), ev_node_int(ia, 2, 1), 1), 0, &lw);
        ok("if (5) takes the then arm",          t5.tag == EV_INT && t5.body.as_int == 1);
        EValue f0 = run_node(ia, ev_node_if(ia, ev_node_int(ia, 0, 1),
                                            ev_node_int(ia, 1, 1), ev_node_int(ia, 2, 1), 1), 0, &lw);
        ok("if (0) takes the else arm",          f0.tag == EV_INT && f0.body.as_int == 2);
        EValue te = run_node(ia, ev_node_if(ia, ev_node_text(ia, "", 1),
                                            ev_node_int(ia, 1, 1), ev_node_int(ia, 2, 1), 1), 0, &lw);
        ok("if (\"\") takes the else arm",         te.tag == EV_INT && te.body.as_int == 2);
        EValue dz = run_node(ia, ev_node_binop(ia, EV_NODE_DIV, ev_node_int(ia, 1, 1),
                                               ev_node_int(ia, 0, 1), 1), 0, &lw);
        ok("1/0 is z, not a number",             dz.tag == EV_VOID);
        ev_arena_free(ia);
    }

    /* ── Lowering refuses what the C interpreter cannot represent ── */
    printf("\nLowering refusals\n");
    {
        int lw = 1;
        EvArena *ra = ev_arena_new("refuse-test");
        EvNode *lst = ev_node_new(ra, EV_NODE_LIST, 1);
        ev_node_add_child(lst, ev_node_int(ra, 1, 1));
        ev_node_add_child(lst, ev_node_int(ra, 2, 1));
        run_node(ra, lst, 0, &lw);
        ok("list literal is refused",            lw == 0);

        char longtxt[300];
        memset(longtxt, 'a', 299); longtxt[299] = '\0';
        run_node(ra, ev_node_text(ra, longtxt, 1), 0, &lw);
        ok("300-byte text literal is refused",   lw == 0);

        char fit[192];
        memset(fit, 'b', 191); fit[191] = '\0';
        EValue ft = run_node(ra, ev_node_text(ra, fit, 1), 0, &lw);
        ok("191-byte text literal lowers whole", lw && ft.tag == EV_TEXT && strlen(ft.text) == 191);

        run_node(ra, ev_node_new(ra, EV_NODE_ANCHOR, 1), 0, &lw);
        ok("anchor node is refused",             lw == 0);

        EValue zz = run_node(ra, ev_node_new(ra, EV_NODE_Z, 1), 0, &lw);
        ok("explicit z lowers to z",             lw && zz.tag == EV_VOID);
        ev_arena_free(ra);
    }

    /* ── Large programs keep every term, or refuse ── */
    printf("\nLarge programs\n");
    {
        int lw = 0;
        EvArena *sa = ev_arena_new("scale-test");
        EvNode *acc = if_term(sa);
        for (int i = 1; i < 120; i++) acc = sum_node(sa, acc, if_term(sa));
        EValue s120 = run_node(sa, acc, 0, &lw);
        ok("120 IF terms sum to 120",            lw && s120.tag == EV_INT && s120.body.as_int == 120);
        ev_arena_free(sa);

        EvArena *ba = ev_arena_new("big-test");
        EvNode *big = if_term(ba);
        for (int i = 1; i < 400; i++) big = sum_node(ba, big, if_term(ba));
        EValue s400 = run_node(ba, big, 0, &lw);
        ok("400 IF terms are refused or sum to 400",
           !lw || (s400.tag == EV_INT && s400.body.as_int == 400));
        ev_arena_free(ba);
    }

    /* ── Function table and call arity ── */
    printf("\nFunction table and call arity\n");
    {
        int lw = 0;
        EvArena *fa = ev_arena_new("func-test");
        EvNode *fargs[17];
        char names[17][8];
        for (int i = 0; i < 17; i++) {
            snprintf(names[i], sizeof names[i], "f%d", i);
            fargs[i] = ev_node_def(fa, names[i], NULL, 0, ev_node_int(fa, i, 1), 1);
        }
        EvModule *fm = ev_lower_module("many", ev_node_call(fa, "holder", fargs, 17, 1));
        ok("17 definitions are all registered",  fm && fm->nfuncs == 17);
        if (fm) {
            EvInterp *fip = ev_interp_new(fm);
            EValue v16 = ev_interp_call(fip, "f16", NULL, 0);
            ok("the 17th function is callable",  v16.tag == EV_INT && v16.body.as_int == 16);
            ev_interp_free(fip);
            ev_module_free(fm);
        }

        EvNode *cargs[17];
        for (int i = 0; i < 17; i++) cargs[i] = ev_node_int(fa, i + 1, 1);
        EvModule *cm = ev_lower_module("c17", ev_node_call(fa, "nosuch", cargs, 17, 1));
        int nargs_seen = -1;
        if (cm) {
            EvBlock *cb = cm->global_body->blocks[0];
            for (int32_t i = 0; i < cb->len; i++)
                if (cb->instrs[i].op == OP_CALL) nargs_seen = cb->instrs[i].nargs;
            ev_module_free(cm);
        }
        ok("a 17-argument call keeps all 17",    nargs_seen == 17);
        (void)lw;
        ev_arena_free(fa);
    }

    printf("\nHEAL STRATEGY\n");
    {
        /* the strategy selects among archived repairs: tied first, then a wildcard */
        EvRepairRegistry *prev = g_repair_registry;
        g_repair_registry = ev_repair_registry_new(NULL);
        add_test_repair(g_repair_registry, "division by zero", "1", 0, "plain");
        add_test_repair(g_repair_registry, "division by zero", "2", 0, "other");
        add_test_repair(g_repair_registry, "division by zero", "3", 0, NULL);
        EvArena *sa = ev_arena_new("heal-strategy");
        int slw = 0;
        EValue r_plain = run_node(sa, heal_with(sa, ev_node_binop(sa, EV_NODE_DIV,
                                                ev_node_int(sa, 1, 1), ev_node_int(sa, 0, 1), 1),
                                                "plain", ev_node_int(sa, 50, 1)), 0, &slw);
        ok("strategy 'plain' selects its tied repair (1)", r_plain.tag == EV_INT && r_plain.body.as_int == 1);
        EValue r_other = run_node(sa, heal_with(sa, ev_node_binop(sa, EV_NODE_DIV,
                                                ev_node_int(sa, 1, 1), ev_node_int(sa, 0, 1), 1),
                                                "other", ev_node_int(sa, 50, 1)), 0, &slw);
        ok("strategy 'other' selects its tied repair (2)", r_other.tag == EV_INT && r_other.body.as_int == 2);
        EValue r_nope = run_node(sa, heal_with(sa, ev_node_binop(sa, EV_NODE_DIV,
                                               ev_node_int(sa, 1, 1), ev_node_int(sa, 0, 1), 1),
                                               "nope", ev_node_int(sa, 50, 1)), 0, &slw);
        ok("an unmatched strategy takes the wildcard (3)", r_nope.tag == EV_INT && r_nope.body.as_int == 3);
        ev_arena_free(sa);
        ev_repair_registry_free(g_repair_registry);
        g_repair_registry = prev;
    }

    printf("\n=== EvTAC: %d passed, %d failed ===\n\n", ok_n, fail_n);
    return fail_n==0 ? 0 : 1;
}

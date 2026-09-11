"""Successor completion-visibility checker: source contracts."""

from __future__ import annotations


from .constants import (
    APPENDIX_WORDS,
    BOUND_ON_LINKED_IMAGE,
    BUILD_ID,
    COMMAND_SYMBOL,
    CONVERGE_SYMBOL,
    DEFERRED_TO_LINKED_IMAGE,
    ENTRY_SYMBOL,
    MAILBOX_VALID,
    PRIMARY_SYMBOL,
    QSIZE_EXPECTED,
    RESIDUAL_LIMITATIONS,
    RUNNER_STOCK_FUNCTION_POINTERS,
    RUNNER_STOCK_VECTOR_SLOTS,
    SCHEMA_VERSION,
    VARIANTS,
)

from .errors import (
    fail,
)

from .c_lexical import (
    _normalize_newlines,
    _sha256_text,
    code_find,
    function_span,
    function_text,
    mask_c_lexical,
    normalized_digest,
    parse_defines,
    require_primary_token_spelling,
    require_stable_contract_defines,
)

from .c_addresses import (
    enclosing_function,
    extract_loop,
    file_scope_text,
    function_spans,
    mmio_macro_kinds,
    mmio_macro_names,
    require_no_compound_literal,
    require_no_critical_lvalue_macro,
    require_no_macro_mmio,
    require_no_statement_macro,
    require_no_token_paste,
)

from .source_loops import (
    queue_programming_sites,
    verify_convergence_contract,
    verify_hard_bypass_contract,
    verify_pre_run_contract,
    verify_primary_contract,
)

from .source_storage import (
    require_authorized_appendix_producers,
    require_every_appendix_word_produced,
    require_no_call_through_pointer_object,
    require_no_function_pointer,
    require_no_indirect_call,
    verify_mailbox_contract,
    verify_observation_contract,
    verify_runner_contract,
    verify_variant_identity,
)

from .source_cleanup import (
    verify_cleanup_contract,
)

from .source_confinement import (
    _return_code_writes,
    require_accessor_designations_confined,
    require_appendix_value_provenance,
    require_cleanup_epilogue,
    require_convergence_classification,
    require_convergence_declarations,
    require_convergence_same_iteration,
    require_entry_return_code_frozen,
    require_isr_register_values,
    require_mailbox_storage_closed,
    require_measured_locals_not_stepped,
    require_no_qread_write,
    require_publication_call_provenance,
    require_qread_load_budget,
    require_register_confinement,
    require_return_expression_provenance,
    require_transport_reset_polarity,
    require_transport_validity_polarity,
    require_wait_for_irq_unreachable,
    require_whole_unit_mmio_confinement,
)


def unbound_claims() -> tuple[str, ...]:
    return tuple(
        claim
        for claim in DEFERRED_TO_LINKED_IMAGE
        if not claim.startswith(tuple(name + ":" for name in BOUND_ON_LINKED_IMAGE))
    )


def identity_matches(
    *,
    schema_version: int,
    build_id: int,
    appendix_words: int,
    qsize_expected: int,
    mailbox_valid: int,
) -> bool:
    """Report whether a candidate identity tuple is the frozen V14 one."""

    return (
        schema_version == SCHEMA_VERSION
        and build_id == BUILD_ID
        and appendix_words == APPENDIX_WORDS
        and qsize_expected == QSIZE_EXPECTED
        and mailbox_valid == MAILBOX_VALID
    )


def verify_generated_sources(runner_text: str, vendor_text: str, variant: str) -> dict[str, object]:
    """Verify a generated Q/QS/SQ source pair and return its fixture manifest."""

    if variant not in VARIANTS:
        raise fail("unknown variant %r" % variant)
    runner_text = _normalize_newlines(runner_text)
    vendor_text = _normalize_newlines(vendor_text)
    vendor_masked = mask_c_lexical(vendor_text)
    runner_masked = mask_c_lexical(runner_text)
    # First, because every scan below -- the lexical mask included -- reads the
    # primary spelling of the punctuators. A source written with a trigraph or a
    # digraph is one this gate is tokenizing differently from the compiler, and
    # nothing derived from that reading is evidence about the built image.
    require_primary_token_spelling(vendor_text, "the vendor translation unit")
    require_primary_token_spelling(runner_text, "the runner translation unit")
    # Every rule below reads a macro's value once. That is only sound while the
    # macro holds one value for the whole translation unit, so the preprocessing
    # history is settled before anything is derived from it.
    require_stable_contract_defines(vendor_masked, "the vendor translation unit")
    require_stable_contract_defines(runner_masked, "the runner translation unit")
    # A macro body is code this gate never expands, so a store written in one is
    # a store no rule below can see. Settled here, with the rest of the
    # preprocessing history, rather than left to each rule to miss separately.
    require_no_statement_macro(vendor_masked, "the vendor translation unit")
    require_no_statement_macro(runner_masked, "the runner translation unit")
    # And a macro body that is only the *lvalue* is the same defect with the
    # store operator moved one token to the right, so it is settled here too.
    require_no_critical_lvalue_macro(vendor_masked, "the vendor translation unit")
    require_no_critical_lvalue_macro(runner_masked, "the runner translation unit")
    # And an initializer with no declarator in front of it is storage the
    # declarator walk has no name to bind, which is the same defect with the
    # name removed instead of the operator.
    require_no_compound_literal(vendor_masked, "the vendor translation unit")
    require_no_compound_literal(runner_masked, "the runner translation unit")
    # A call whose callee is an expression carries any effect past every rule
    # below, so it is settled here with the other things this gate refuses to
    # model rather than left to each counting rule to miss separately.
    # Vendor-side only. The measured path, the submit count and the register
    # confinement all live in the vendor translation unit, and the host runner
    # this contract is generated against legitimately declares an
    # ``irq_handler_t`` function pointer of its own -- refusing that would refuse
    # the stock file rather than an attack. What the runner publishes is closed
    # by its own record, copy and validity rules instead.
    require_no_function_pointer(vendor_masked, "the vendor translation unit")
    require_no_indirect_call(vendor_masked, "the vendor translation unit")
    # The runner gets the same two rules, minus the one name the stock file
    # legitimately declares. Exempting the *translation unit* was what admitted a
    # function pointer at the runner's file scope -- which, composed with a
    # publication or reset symbol taken by address, is a call this gate cannot
    # follow reaching the transport it just proved. Exempting the stock name
    # instead keeps the frozen ``irq_handler_t`` and refuses every other one.
    require_no_function_pointer(
        runner_masked, "the runner translation unit", RUNNER_STOCK_FUNCTION_POINTERS
    )
    require_no_indirect_call(runner_masked, "the runner translation unit")
    # The exemption above admits the stock vector *type*. An object of that type
    # is called with the syntax of a direct call, so the indirect-call rule
    # cannot see it and this is what refuses it.
    require_no_call_through_pointer_object(
        runner_masked,
        RUNNER_STOCK_FUNCTION_POINTERS,
        "the runner translation unit",
        RUNNER_STOCK_VECTOR_SLOTS,
    )
    defines = parse_defines(vendor_masked)

    pre_run = verify_pre_run_contract(vendor_masked, defines)
    primary = verify_primary_contract(vendor_masked, variant, defines)
    hard_bypass = verify_hard_bypass_contract(vendor_masked)
    convergence = verify_convergence_contract(vendor_masked, defines)
    mailbox = verify_mailbox_contract(vendor_masked, defines)
    # The appendix words are copies of observation-record fields, so the
    # producer table that closes the mailbox is only a proof while the record it
    # copies from is closed too.
    verify_observation_contract(vendor_masked, variant, defines)
    identity = verify_variant_identity(vendor_masked, defines, variant)
    cleanup = verify_cleanup_contract(vendor_masked, vendor_text, variant, defines)
    runner = verify_runner_contract(runner_masked)
    # Last, so a source that breaks a named rule is reported by that rule rather
    # than by the absence its breakage happens to leave behind.
    produced_words = require_every_appendix_word_produced(vendor_masked, defines)
    # Having *a* producer is the fail-silent half. Having only the producers the
    # design gives it is the fail-open one, and it runs after the specific rules
    # so a source that breaks one of them is still named by that rule.
    appendix_stores = require_authorized_appendix_producers(vendor_masked, defines)
    # And having the design's producers is still only a proof about *where*. This
    # is the proof about *what*: 28 of the 34 words accepted an attacker-chosen
    # constant while every site and count rule above stayed satisfied.
    appendix_valued = require_appendix_value_provenance(vendor_masked, defines)
    # Words 20..23 are the publisher's parameters, so their value proof ends at
    # the call site; this is where it continues.
    publication_calls = require_publication_call_provenance(vendor_masked)
    require_cleanup_epilogue(
        vendor_masked[function_span(vendor_masked, "test_commands", "command function")[0] :
                      function_span(vendor_masked, "test_commands", "command function")[1]]
    )
    # The epilogue decides the code, and this is the frame that returns it -- but
    # it is not V14's frame. The frozen vendor rewrites the same variable after
    # the command function has returned: ``ret_code = 2`` on an output-verify
    # mismatch, ``ret_code = 3`` on an IRQ-mask mismatch, and ``ret_code++`` when
    # the IRQ never fired. Demanding that this frame leave the value alone was a
    # rule the design never stated, calibrated against a stand-in vendor that had
    # none of those stores, and it cannot be satisfied without editing frozen
    # vendor code.
    #
    # It is also not load-bearing. The V14 verdict travels in the mailbox behind
    # the V14_MAILBOX_VALID magic, which is what the runner copies its phase,
    # reason and tuple from; the vendor return code only raises a telemetry flag.
    # What survives is that the two must never be confused, because the vendor's
    # codes collide numerically with V14_RET_*, so that is stated in the manifest
    # rather than enforced as a shape the vendor cannot have.
    entry_text = function_text(vendor_masked, ENTRY_SYMBOL, "entry function")
    require_entry_return_code_frozen(entry_text, "entry")
    entry_perturbing_stores = _return_code_writes(entry_text)
    # And settling the variable is not settling the verdict: the host is handed
    # whatever the ``return`` evaluates, which no assignment rule above reads.
    returned_expressions = sum(
        require_return_expression_provenance(
            function_text(vendor_masked, name, label), name, label, defines
        )
        for name, label in ((COMMAND_SYMBOL, "command"), (ENTRY_SYMBOL, "entry"))
    )
    # The appendix is a transport object like the other two, and it is the one
    # that was not closed against a write that names no word.
    require_mailbox_storage_closed(vendor_masked, defines, "the vendor translation unit")
    require_mailbox_storage_closed(runner_masked, defines, "the runner translation unit")
    require_transport_validity_polarity(runner_masked)
    # The arm rule proves the branch that settles the flag; this proves the store
    # that re-arms it before the run, which the count above left unread.
    require_transport_reset_polarity(runner_masked)
    # Last of the whole-unit rules: every NPU register named where the design
    # does not name it, which is what makes the running-path counts above
    # statements about the translation unit rather than about one function.
    setup_owner = sorted(
        {
            enclosing_function(function_spans(vendor_masked), site)
            for site in queue_programming_sites(
                vendor_masked, defines, file_scope_text(vendor_masked), function_spans(vendor_masked)
            )
        }
    )[0]
    # Before the confinement walks: a QREAD *write* is refused for what it does
    # to the queue, not for where it sits, and reporting it by owner would name
    # a source by the weaker of the two things wrong with it.
    require_no_qread_write(vendor_masked)
    # Owning the register says where it may be loaded; this says how often, so a
    # load inside an authorised owner but outside the structure that measures it
    # is refused rather than counted as nothing.
    qread_loads = require_qread_load_budget(
        vendor_masked, defines, setup_owner, variant
    )
    register_designations = require_register_confinement(vendor_masked, setup_owner, variant)
    # And the same question asked of every spelling that carries no register
    # name: a numeric offset, an absolute address, a macro alias. Without these
    # three, "confined" is a claim about the tokens ``NPU_REG_*`` rather than
    # about the translation unit the manifest says it is about.
    require_no_macro_mmio(
        vendor_masked,
        mmio_macro_names(vendor_masked),
        "the vendor translation unit",
        mmio_macro_kinds(vendor_masked),
    )
    register_accesses = require_whole_unit_mmio_confinement(
        vendor_masked, defines, setup_owner, variant
    )
    # And the third spelling: the register carried as the accessor's own
    # argument, which neither the name scan nor the address resolver reads.
    accessor_designations_confined = require_accessor_designations_confined(
        vendor_masked, defines, setup_owner, variant
    )
    # After the designation rules, so a paste that *does* name a register or an
    # offset is still reported by the rule that owns designations, and only a
    # name this gate genuinely cannot compute is reported as one.
    require_no_token_paste(vendor_masked, "the vendor translation unit")
    require_no_token_paste(runner_masked, "the runner translation unit")
    require_isr_register_values(vendor_masked, defines)
    require_wait_for_irq_unreachable(vendor_masked)
    converge_body = function_text(vendor_masked, CONVERGE_SYMBOL, "common convergence helper")
    require_convergence_classification(converge_body)
    # Before the count rule below, so a local the design assigns once and a
    # mutation steps is named by the stepping rule rather than by the count it
    # happens to leave intact.
    require_measured_locals_not_stepped(converge_body, "the common convergence helper")
    require_measured_locals_not_stepped(
        function_text(vendor_masked, PRIMARY_SYMBOL[variant], "primary helper"),
        "the primary helper",
    )
    require_convergence_same_iteration(
        extract_loop(converge_body, "common convergence helper")[1]
    )
    # Last of the convergence rules, so a source that breaks one of the named
    # ones above is reported by that rule rather than by the count it leaves
    # behind.
    require_convergence_declarations(converge_body, defines)
    command_start, command_stop = function_span(vendor_masked, "test_commands", "command function")
    command = vendor_masked[command_start:command_stop]
    tail_start = code_find(command, "v14_publish_primary(")
    if tail_start < 0:
        raise fail("common tail does not start at the shared primary publication")

    doc: dict[str, object] = {
        "variant": variant,
        "variant_id": VARIANTS[variant],
        "schema_version": SCHEMA_VERSION,
        "build_id": "0x%08X" % BUILD_ID,
        "qualification": "UNIT-QUALIFIED",
        "proof_scope": "generated_source_and_fixture_only",
        "real_elf_qualified": False,
        # This gate is handed generated text, not the frozen inputs, so it is
        # still not the thing that checks the raw vendor pin -- the build graph's
        # frozen-input evidence and the unit suite do that against the tracked
        # firmware/Drivers/u85_driver/u85.c.
        "vendor_raw_source_verified": False,
        # The vendor rewrites its own return code after the command function has
        # returned, and its values collide numerically with V14_RET_*. The V14
        # verdict is the mailbox behind V14_MAILBOX_VALID; this code is not it,
        # and a consumer that classifies run_rc as a V14 phase is reading vendor
        # telemetry as a diagnostic result.
        "vendor_entry_return_code_stores": len(entry_perturbing_stores),
        "vendor_entry_return_code_is_not_the_v14_verdict": True,
        "residual_limitations": list(RESIDUAL_LIMITATIONS),
        "deferred_to_linked_image": list(DEFERRED_TO_LINKED_IMAGE),
        "bound_on_linked_image": list(BOUND_ON_LINKED_IMAGE),
        # Named, not proven by anyone yet. An empty list is the goal; a
        # non-empty one is what a reader of UNIT-QUALIFIED has to weigh.
        "unbound_claims": list(unbound_claims()),
        "generated_runner_sha256": _sha256_text(runner_text),
        "generated_vendor_sha256": _sha256_text(vendor_text),
        "common_convergence_source_sha256": normalized_digest(converge_body),
        "common_tail_source_sha256": normalized_digest(command[tail_start:]),
        # The verifier's own count of appendix words it found a producer for.
        # It equals the appendix width or the verdict was a refusal.
        "appendix_words_with_a_producer": produced_words,
        # And its own count of the stores that produced them, outside the reset.
        # A word written twice, or written where the design does not write it,
        # is a refusal rather than a larger number here.
        "appendix_stores_outside_the_reset": appendix_stores,
        # The same count taken again over the *values* those stores write. It
        # equals the store count or the verdict was a refusal, and it is what
        # separates "the design's function wrote this word" from "the design's
        # expression reached it".
        "appendix_stores_with_proven_values": appendix_valued,
        # The publication call sites whose argument tuple the verifier matched.
        "publication_calls_with_proven_arguments": publication_calls,
        # Every NPU register designation in the vendor translation unit that fell
        # inside its authorised function set. A designation outside it is a
        # refusal rather than a larger number here, so this is the whole-unit
        # scope the running-path counts above are true of.
        "vendor_register_designations_confined": register_designations,
        # And the verifier's own count of the resolved MMIO accesses it walked
        # over every function span and file scope -- the spellings that carry no
        # register name at all. An access this gate cannot pin to one register,
        # anywhere in the unit, is a refusal rather than a larger number here,
        # which is what makes the scope below a statement about the translation
        # unit rather than about the ``NPU_REG_*`` tokens in it.
        "vendor_register_accesses_confined": register_accesses,
        # And the third spelling, counted the same way: the register carried as
        # the vendor accessor's own argument. An accessor call this gate cannot
        # resolve to one register, anywhere in the unit, is a refusal rather
        # than a larger number here -- without which "confined" would still be a
        # claim about pointer expressions and ``NPU_REG_*`` tokens rather than
        # about every access the unit makes.
        "vendor_accessor_designations_confined": accessor_designations_confined,
        "register_confinement_scope": "vendor_translation_unit",
        # The verifier's own count of the return statements it matched against
        # the design's table, across the two frames that carry a vendor return
        # code. A return expression outside the table is a refusal rather than a
        # larger number here, so the settled return code and the value the host
        # is handed are the same statement.
        "vendor_return_expressions_with_proven_values": returned_expressions,
        # The verifier's own count of the QREAD accesses it walked inside the
        # owners the design authorises. An owner that loads it more often than
        # the design does is a refusal rather than a larger number here, which
        # is what makes the confinement a statement about the loads and not only
        # about the functions.
        "vendor_qread_loads_within_budget": qread_loads,
    }
    for section in (pre_run, primary, hard_bypass, convergence, mailbox, identity, cleanup, runner):
        doc.update(section)
    return doc

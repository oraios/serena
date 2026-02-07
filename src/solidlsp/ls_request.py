from typing import TYPE_CHECKING, Any, Union

from solidlsp.lsp_protocol_handler import lsp_types

if TYPE_CHECKING:
    from .ls_handler import LanguageServerProcess


class LanguageServerRequest:
    def __init__(self, handler: "LanguageServerProcess"):
        self.handler = handler

    def _send_request(self, method: str, params: Any | None = None) -> Any:
        return self.handler.send_request(method, params)

    def implementation(self, params: lsp_types.ImplementationParams) -> Union["lsp_types.Definition", list["lsp_types.LocationLink"], None]:
        """A request to resolve the implementation locations of a symbol at a given text
        document position. The request's parameter is of type [TextDocumentPositionParams]
        (#TextDocumentPositionParams) the response is of type {@link Definition} or a
        Thenable that resolves to such.
        """
        return self._send_request("textDocument/implementation", params)

    def type_definition(
        self, params: lsp_types.TypeDefinitionParams
    ) -> Union["lsp_types.Definition", list["lsp_types.LocationLink"], None]:
        """A request to resolve the type definition locations of a symbol at a given text
        document position. The request's parameter is of type [TextDocumentPositionParams]
        (#TextDocumentPositionParams) the response is of type {@link Definition} or a
        Thenable that resolves to such.
        """
        return self._send_request("textDocument/typeDefinition", params)

    def document_color(self, params: lsp_types.DocumentColorParams) -> list["lsp_types.ColorInformation"]:
        """A request to list all color symbols found in a given text document. The request's
        parameter is of type {@link DocumentColorParams} the
        response is of type {@link ColorInformation ColorInformation[]} or a Thenable
        that resolves to such.
        """
        return self._send_request("textDocument/documentColor", params)

    def color_presentation(self, params: lsp_types.ColorPresentationParams) -> list["lsp_types.ColorPresentation"]:
        """A request to list all presentation for a color. The request's
        parameter is of type {@link ColorPresentationParams} the
        response is of type {@link ColorInformation ColorInformation[]} or a Thenable
        that resolves to such.
        """
        return self._send_request("textDocument/colorPresentation", params)

    def folding_range(self, params: lsp_types.FoldingRangeParams) -> list["lsp_types.FoldingRange"] | None:
        """A request to provide folding ranges in a document. The request's
        parameter is of type {@link FoldingRangeParams}, the
        response is of type {@link FoldingRangeList} or a Thenable
        that resolves to such.
        """
        return self._send_request("textDocument/foldingRange", params)

    def declaration(self, params: lsp_types.DeclarationParams) -> Union["lsp_types.Declaration", list["lsp_types.LocationLink"], None]:
        """A request to resolve the type definition locations of a symbol at a given text
        document position. The request's parameter is of type [TextDocumentPositionParams]
        (#TextDocumentPositionParams) the response is of type {@link Declaration}
        or a typed array of {@link DeclarationLink} or a Thenable that resolves
        to such.
        """
        return self._send_request("textDocument/declaration", params)

    def selection_range(self, params: lsp_types.SelectionRangeParams) -> list["lsp_types.SelectionRange"] | None:
        """A request to provide selection ranges in a document. The request's
        parameter is of type {@link SelectionRangeParams}, the
        response is of type {@link SelectionRange SelectionRange[]} or a Thenable
        that resolves to such.
        """
        return self._send_request("textDocument/selectionRange", params)

    def prepare_call_hierarchy(self, params: lsp_types.CallHierarchyPrepareParams) -> list["lsp_types.CallHierarchyItem"] | None:
        """A request to result a `CallHierarchyItem` in a document at a given position.
        Can be used as an input to an incoming or outgoing call hierarchy.

        @since 3.16.0
        """
        return self._send_request("textDocument/prepareCallHierarchy", params)

    def incoming_calls(self, params: lsp_types.CallHierarchyIncomingCallsParams) -> list["lsp_types.CallHierarchyIncomingCall"] | None:
        """A request to resolve the incoming calls for a given `CallHierarchyItem`.

        @since 3.16.0
        """
        return self._send_request("callHierarchy/incomingCalls", params)

    def outgoing_calls(self, params: lsp_types.CallHierarchyOutgoingCallsParams) -> list["lsp_types.CallHierarchyOutgoingCall"] | None:
        """A request to resolve the outgoing calls for a given `CallHierarchyItem`.

        @since 3.16.0
        """
        return self._send_request("callHierarchy/outgoingCalls", params)

    def semantic_tokens_full(self, params: lsp_types.SemanticTokensParams) -> Union["lsp_types.SemanticTokens", None]:
        """@since 3.16.0"""
        return self._send_request("textDocument/semanticTokens/full", params)

    def semantic_tokens_delta(
        self, params: lsp_types.SemanticTokensDeltaParams
    ) -> Union["lsp_types.SemanticTokens", "lsp_types.SemanticTokensDelta", None]:
        """@since 3.16.0"""
        return self._send_request("textDocument/semanticTokens/full/delta", params)

    def semantic_tokens_range(self, params: lsp_types.SemanticTokensRangeParams) -> Union["lsp_types.SemanticTokens", None]:
        """@since 3.16.0"""
        return self._send_request("textDocument/semanticTokens/range", params)

    def linked_editing_range(self, params: lsp_types.LinkedEditingRangeParams) -> Union["lsp_types.LinkedEditingRanges", None]:
        """A request to provide ranges that can be edited together.

        @since 3.16.0
        """
        return self._send_request("textDocument/linkedEditingRange", params)

    def will_create_files(self, params: lsp_types.CreateFilesParams) -> Union["lsp_types.WorkspaceEdit", None]:
        """The will create files request is sent from the client to the server before files are actually
        created as long as the creation is triggered from within the client.

        @since 3.16.0
        """
        return self._send_request("workspace/willCreateFiles", params)

    def will_rename_files(self, params: lsp_types.RenameFilesParams) -> Union["lsp_types.WorkspaceEdit", None]:
        """The will rename files request is sent from the client to the server before files are actually
        renamed as long as the rename is triggered from within the client.

        @since 3.16.0
        """
        return self._send_request("workspace/willRenameFiles", params)

    def will_delete_files(self, params: lsp_types.DeleteFilesParams) -> Union["lsp_types.WorkspaceEdit", None]:
        """The did delete files notification is sent from the client to the server when
        files were deleted from within the client.

        @since 3.16.0
        """
        return self._send_request("workspace/willDeleteFiles", params)

    def moniker(self, params: lsp_types.MonikerParams) -> list["lsp_types.Moniker"] | None:
        """A request to get the moniker of a symbol at a given text document position.
        The request parameter is of type {@link TextDocumentPositionParams}.
        The response is of type {@link Moniker Moniker[]} or `null`.
        """
        return self._send_request("textDocument/moniker", params)

    def prepare_type_hierarchy(self, params: lsp_types.TypeHierarchyPrepareParams) -> list["lsp_types.TypeHierarchyItem"] | None:
        """A request to result a `TypeHierarchyItem` in a document at a given position.
        Can be used as an input to a subtypes or supertypes type hierarchy.

        @since 3.17.0
        """
        return self._send_request("textDocument/prepareTypeHierarchy", params)

    def type_hierarchy_supertypes(self, params: lsp_types.TypeHierarchySupertypesParams) -> list["lsp_types.TypeHierarchyItem"] | None:
        """A request to resolve the supertypes for a given `TypeHierarchyItem`.

        @since 3.17.0
        """
        return self._send_request("typeHierarchy/supertypes", params)

    def type_hierarchy_subtypes(self, params: lsp_types.TypeHierarchySubtypesParams) -> list["lsp_types.TypeHierarchyItem"] | None:
        """A request to resolve the subtypes for a given `TypeHierarchyItem`.

        @since 3.17.0
        """
        return self._send_request("typeHierarchy/subtypes", params)

    def inline_value(self, params: lsp_types.InlineValueParams) -> list["lsp_types.InlineValue"] | None:
        """A request to provide inline values in a document. The request's parameter is of
        type {@link InlineValueParams}, the response is of type
        {@link InlineValue InlineValue[]} or a Thenable that resolves to such.

        @since 3.17.0
        """
        return self._send_request("textDocument/inlineValue", params)

    def inlay_hint(self, params: lsp_types.InlayHintParams) -> list["lsp_types.InlayHint"] | None:
        """A request to provide inlay hints in a document. The request's parameter is of
        type {@link InlayHintsParams}, the response is of type
        {@link InlayHint InlayHint[]} or a Thenable that resolves to such.

        @since 3.17.0
        """
        return self._send_request("textDocument/inlayHint", params)

    def resolve_inlay_hint(self, params: lsp_types.InlayHint) -> "lsp_types.InlayHint":
        """A request to resolve additional properties for an inlay hint.
        The request's parameter is of type {@link InlayHint}, the response is
        of type {@link InlayHint} or a Thenable that resolves to such.

        @since 3.17.0
        """
        return self._send_request("inlayHint/resolve", params)

    def text_document_diagnostic(self, params: lsp_types.DocumentDiagnosticParams) -> "lsp_types.DocumentDiagnosticReport":
        """The document diagnostic request definition.

        @since 3.17.0
        """
        return self._send_request("textDocument/diagnostic", params)

    def workspace_diagnostic(self, params: lsp_types.WorkspaceDiagnosticParams) -> "lsp_types.WorkspaceDiagnosticReport":
        """The workspace diagnostic request definition.

        @since 3.17.0
        """
        return self._send_request("workspace/diagnostic", params)

    def initialize(self, params: lsp_types.InitializeParams) -> "lsp_types.InitializeResult":
        """The initialize request is sent from the client to the server.
        It is sent once as the request after starting up the server.
        The requests parameter is of type {@link InitializeParams}
        the response if of type {@link InitializeResult} of a Thenable that
        resolves to such.
        """
        return self._send_request("initialize", params)

    def shutdown(self) -> None:
        """A shutdown request is sent from the client to the server.
        It is sent once when the client decides to shutdown the
        server. The only notification that is sent after a shutdown request
        is the exit event.
        """
        return self._send_request("shutdown")

    def will_save_wait_until(self, params: lsp_types.WillSaveTextDocumentParams) -> list["lsp_types.TextEdit"] | None:
        """A document will save request is sent from the client to the server before
        the document is actually saved. The request can return an array of TextEdits
        which will be applied to the text document before it is saved. Please note that
        clients might drop results if computing the text edits took too long or if a
        server constantly fails on this request. This is done to keep the save fast and
        reliable.
        """
        return self._send_request("textDocument/willSaveWaitUntil", params)

    def completion(self, params: lsp_types.CompletionParams) -> Union[list["lsp_types.CompletionItem"], "lsp_types.CompletionList", None]:
        """Request to request completion at a given text document position. The request's
        parameter is of type {@link TextDocumentPosition} the response
        is of type {@link CompletionItem CompletionItem[]} or {@link CompletionList}
        or a Thenable that resolves to such.

        The request can delay the computation of the {@link CompletionItem.detail `detail`}
        and {@link CompletionItem.documentation `documentation`} properties to the `completionItem/resolve`
        request. However, properties that are needed for the initial sorting and filtering, like `sortText`,
        `filterText`, `insertText`, and `textEdit`, must not be changed during resolve.
        """
        return self._send_request("textDocument/completion", params)

    def resolve_completion_item(self, params: lsp_types.CompletionItem) -> "lsp_types.CompletionItem":
        """Request to resolve additional information for a given completion item.The request's
        parameter is of type {@link CompletionItem} the response
        is of type {@link CompletionItem} or a Thenable that resolves to such.
        """
        return self._send_request("completionItem/resolve", params)

    def hover(self, params: lsp_types.HoverParams) -> Union["lsp_types.Hover", None]:
        """Request to request hover information at a given text document position. The request's
        parameter is of type {@link TextDocumentPosition} the response is of
        type {@link Hover} or a Thenable that resolves to such.
        """
        return self._send_request("textDocument/hover", params)

    def signature_help(self, params: lsp_types.SignatureHelpParams) -> Union["lsp_types.SignatureHelp", None]:
        return self._send_request("textDocument/signatureHelp", params)

    def definition(self, params: lsp_types.DefinitionParams) -> Union["lsp_types.Definition", list["lsp_types.LocationLink"], None]:
        """A request to resolve the definition location of a symbol at a given text
        document position. The request's parameter is of type [TextDocumentPosition]
        (#TextDocumentPosition) the response is of either type {@link Definition}
        or a typed array of {@link DefinitionLink} or a Thenable that resolves
        to such.
        """
        return self._send_request("textDocument/definition", params)

    def references(self, params: lsp_types.ReferenceParams) -> list["lsp_types.Location"] | None:
        """A request to resolve project-wide references for the symbol denoted
        by the given text document position. The request's parameter is of
        type {@link ReferenceParams} the response is of type
        {@link Location Location[]} or a Thenable that resolves to such.
        """
        return self._send_request("textDocument/references", params)

    def document_highlight(self, params: lsp_types.DocumentHighlightParams) -> list["lsp_types.DocumentHighlight"] | None:
        """Request to resolve a {@link DocumentHighlight} for a given
        text document position. The request's parameter is of type [TextDocumentPosition]
        (#TextDocumentPosition) the request response is of type [DocumentHighlight[]]
        (#DocumentHighlight) or a Thenable that resolves to such.
        """
        return self._send_request("textDocument/documentHighlight", params)

    def document_symbol(
        self, params: lsp_types.DocumentSymbolParams
    ) -> list["lsp_types.SymbolInformation"] | list["lsp_types.DocumentSymbol"] | None:
        """A request to list all symbols found in a given text document. The request's
        parameter is of type {@link TextDocumentIdentifier} the
        response is of type {@link SymbolInformation SymbolInformation[]} or a Thenable
        that resolves to such.
        """
        return self._send_request("textDocument/documentSymbol", params)

    def code_action(self, params: lsp_types.CodeActionParams) -> list[Union["lsp_types.Command", "lsp_types.CodeAction"]] | None:
        """A request to provide commands for the given text document and range."""
        return self._send_request("textDocument/codeAction", params)

    def resolve_code_action(self, params: lsp_types.CodeAction) -> "lsp_types.CodeAction":
        """Request to resolve additional information for a given code action.The request's
        parameter is of type {@link CodeAction} the response
        is of type {@link CodeAction} or a Thenable that resolves to such.
        """
        return self._send_request("codeAction/resolve", params)

    def workspace_symbol(
        self, params: lsp_types.WorkspaceSymbolParams
    ) -> list["lsp_types.SymbolInformation"] | list["lsp_types.WorkspaceSymbol"] | None:
        """A request to list project-wide symbols matching the query string given
        by the {@link WorkspaceSymbolParams}. The response is
        of type {@link SymbolInformation SymbolInformation[]} or a Thenable that
        resolves to such.

        @since 3.17.0 - support for WorkspaceSymbol in the returned data. Clients
         need to advertise support for WorkspaceSymbols via the client capability
         `workspace.symbol.resolveSupport`.
        """
        return self._send_request("workspace/symbol", params)

    def resolve_workspace_symbol(self, params: lsp_types.WorkspaceSymbol) -> "lsp_types.WorkspaceSymbol":
        """A request to resolve the range inside the workspace
        symbol's location.

        @since 3.17.0
        """
        return self._send_request("workspaceSymbol/resolve", params)

    def code_lens(self, params: lsp_types.CodeLensParams) -> list["lsp_types.CodeLens"] | None:
        """A request to provide code lens for the given text document."""
        return self._send_request("textDocument/codeLens", params)

    def resolve_code_lens(self, params: lsp_types.CodeLens) -> "lsp_types.CodeLens":
        """A request to resolve a command for a given code lens."""
        return self._send_request("codeLens/resolve", params)

    def document_link(self, params: lsp_types.DocumentLinkParams) -> list["lsp_types.DocumentLink"] | None:
        """A request to provide document links"""
        return self._send_request("textDocument/documentLink", params)

    def resolve_document_link(self, params: lsp_types.DocumentLink) -> "lsp_types.DocumentLink":
        """Request to resolve additional information for a given document link. The request's
        parameter is of type {@link DocumentLink} the response
        is of type {@link DocumentLink} or a Thenable that resolves to such.
        """
        return self._send_request("documentLink/resolve", params)

    def formatting(self, params: lsp_types.DocumentFormattingParams) -> list["lsp_types.TextEdit"] | None:
        """A request to to format a whole document."""
        return self._send_request("textDocument/formatting", params)

    def range_formatting(self, params: lsp_types.DocumentRangeFormattingParams) -> list["lsp_types.TextEdit"] | None:
        """A request to to format a range in a document."""
        return self._send_request("textDocument/rangeFormatting", params)

    def on_type_formatting(self, params: lsp_types.DocumentOnTypeFormattingParams) -> list["lsp_types.TextEdit"] | None:
        """A request to format a document on type."""
        return self._send_request("textDocument/onTypeFormatting", params)

    def rename(self, params: lsp_types.RenameParams) -> Union["lsp_types.WorkspaceEdit", None]:
        """A request to rename a symbol."""
        return self._send_request("textDocument/rename", params)

    def prepare_rename(self, params: lsp_types.PrepareRenameParams) -> Union["lsp_types.PrepareRenameResult", None]:
        """A request to test and perform the setup necessary for a rename.

        @since 3.16 - support for default behavior
        """
        return self._send_request("textDocument/prepareRename", params)

    def execute_command(self, params: lsp_types.ExecuteCommandParams) -> Union["lsp_types.LSPAny", None]:
        """A request send from the client to the server to execute a command. The request might return
        a workspace edit which the client will apply to the workspace.
        """
        return self._send_request("workspace/executeCommand", params)

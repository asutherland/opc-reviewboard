// State variables
var gPublishing = false;
var gPendingSaveCount = 0;
var gPendingDiffFragments = {};
var gReviewBanner = $("#review-banner");
var gDraftBanner = $("#draft-banner");
var gDraftBannerButtons = $("input", gDraftBanner);


/*
 * "complete" signal handlers for various fields, designed to do
 * post-processing of the values for display.
 */
var gEditorCompleteHandlers = {
    'bugs_closed': function(data) {
        if (gBugTrackerURL == "") {
            return data.join(", ");
        } else {
            return urlizeList(data, function(item) {
                return gBugTrackerURL.replace("%s", item);
            });
        }
    },
    'target_groups': function(data) {
        return urlizeList(data,
            function(item) { return item.url; },
            function(item) { return item.name; }
        );
    },
    'target_people': function(data) {
        return urlizeList(data,
            function(item) { return item.url; },
            function(item) { return item.username; }
        );
    },
    'description': linkifyText,
    'testing_done': linkifyText
};


/*
 * Returns the API path to the current review request. This may be an
 * absolute path or a path relative to the /api/json/ tree.
 *
 * @param {bool} fullPath  true if this should be the full, absolute path.
 *
 * @return {string} The API path.
 */
function getReviewRequestAPIPath(fullPath) {
    return (fullPath ? SITE_ROOT + "api/json" : "") +
           "/reviewrequests/" + gReviewRequestId;
}


/*
 * Returns the API path of the current review draft relative to the
 * review request API tree.
 *
 * @return {string} The API path.
 */
function getReviewDraftAPIPath() {
    return "/reviews/draft";
}


/*
 * Returns the API path for diff comments relative to the review request
 * API tree.
 *
 * If dealing with interdiffs, interfilediff_revision and interfilediff_id
 * must not be null. Otherwise, they must both be null.
 *
 * @param {string} filediff_revision       The filediff revision.
 * @param {int}    filediff_id             The filediff ID.
 * @param {string} interfilediff_revision  The optional interfilediff revision.
 * @param {int}    interfilediff_id        The optional interfilediff ID.
 * @param {int}    beginLineNum            The beginning comment line number.
 *
 * @return {string} The API path.
 */
function getDiffAPIPath(filediff_revision, filediff_id,
                        interfilediff_revision, interfilediff_id,
                        beginLineNum) {
    return "/diff/" +
           (interfilediff_revision == null
            ? filediff_revision
            : filediff_revision + "-" + interfilediff_revision) +
           "/file/" +
           (interfilediff_id == null
            ? filediff_id
            : filediff_id + "-" + interfilediff_id) +
           "/line/" + beginLineNum + "/comments/";
}


/*
 * Returns the API path for screenshot comments relative to the review request
 * API tree.
 *
 * @param {int} screenshotId  The screenshot ID.
 * @param {int} x             The comment X location.
 * @param {int} y             The comment Y location.
 * @param {int} width         The comment width.
 * @param {int} height        The comment height.
 *
 * @return {string} The API path.
 */
function getScreenshotAPIPath(screenshotId, x, y, width, height) {
    return "/s/" + screenshotId + "/comments/" + width + "x" + height +
           "+" + x + "+" + y + "/";
}


/*
 * Convenience wrapper for review request API functions. This will handle
 * any button disabling/enabling, write to the correct path prefix, and
 * provides default functionality for reloading the page upon success
 * (unless overridden) and displaying server errors.
 *
 * options has the following fields:
 *
 *    buttons  - An optional list of buttons to disable/enable.
 *    type     - The request type (defaults to "POST").
 *    path     - The relative path to the review request API tree.
 *    data     - Data to send with the request.
 *    success  - An optional success callback. The default one will reload
 *               the page.
 *    error    - An optional error callback, called after the error banner
 *               is displayed.
 *    complete - An optional complete callback, called after the success or
 *               error callbacks.
 *
 * @param {object} options  The options, listed above.
 */
function reviewRequestApiCall(options) {
    options.path = getReviewRequestAPIPath() + options.path;

    if (!options.success) {
        options.success = function() { window.location = gReviewRequestPath; };
    }

    rbApiCall(options);
}


/*
 * Converts an array of items to a list of hyperlinks.
 *
 * By default, this will use the item as the URL and as the hyperlink text.
 * By overriding urlFunc and textFunc, the URL and text can be customized.
 *
 * @param {array}    list     The list of items.
 * @param {function} urlFunc  A function to return the URL for an item in
 *                            the list.
 * @param {function} textFunc A function to return the text for an item in
 *                            the list.
 *
 * @return A string containing the HTML markup for the list of hyperlinks.
 */
function urlizeList(list, urlFunc, textFunc) {
    var str = "";

    for (var i = 0; i < list.length; i++) {
        var item = list[i];
        str += '<a href="';
        str += (urlFunc ? urlFunc(item) : item);
        str += '">';
        str += (textFunc ? textFunc(item) : item);
        str += '</a>';

        if (i < list.length - 1) {
            str += ", ";
        }
    }

    return str;
}


/*
 * Linkifies a block of text, turning URLs, /r/#/ paths, nad bug numbers
 * into clickable links.
 *
 * @param {string} text  The text to linkify.
 *
 * @returns {string} The resulting HTML.
 */
function linkifyText(text) {
    text = text.htmlEncode();

    /* Linkify all URLs. */
    text = text.replace(
        /\b([a-z]+:\/\/[-A-Za-z0-9+&@#\/%?=~_()|!:,.;]*([-A-Za-z0-9+@#\/%=~_();|]|))/g,
        function(url) {
            /*
             * We might catch an entity at the end of the URL. This is hard
             * to avoid, since we can't rely on advanced RegExp techniques
             * in all browsers. So, we'll now search for it and prevent it
             * from being part of the URL if it exists.
             *
             * See bug 1069.
             */
            var extra = "";
            var parts = url.match(/^(.*)(&[a-z]+;)$/);

            if (parts != null) {
                /* We caught an entity. Set it free. */
                url = parts[1];
                extra = parts[2];
            }

            return '<a href="' + url + '">' + url + '</a>' + extra;
        });


    /* Linkify /r/#/ review request numbers */
    text = text.replace(
        /(^|\s|&lt;)\/(r\/\d+(\/[-A-Za-z0-9+&@#\/%?=~_()|!:,.;]*[-A-Za-z0-9+&@#\/%=~_()|])?)/g,
        '$1<a href="' + SITE_ROOT + '$2">/$2</a>');

    /* Bug numbers */
    if (gBugTrackerURL != "") {
        text = text.replace(/\b(bug|issue) (#[^.\s]+|#?\d+)/gi,
            function(m1, m2, m3) {
                return '<a href="' + gBugTrackerURL.replace("%s", m3) +
                       '">' + m1 + '</a>';
            });
    }

    return text;
}


/*
 * Sets a field in the draft.
 *
 * If we're in the process of publishing, this will check if we have saved
 * all fields before publishing the draft.
 *
 * @param {string} field  The field name.
 * @param {string} value  The field value.
 */
function setDraftField(field, value) {
    reviewRequestApiCall({
        path: "/draft/set/" + field + "/",
        buttons: gDraftBannerButtons,
        data: { value: value },
        errorPrefix: "Saving the draft has failed due to a server error:",
        success: function(rsp) {
            var func = gEditorCompleteHandlers[field];

            if ($.isFunction(func)) {
                $("#" + field).html(func(rsp[field]));
            }

            gDraftBanner.show();

            if (gPublishing) {
                gPendingSaveCount--;

                if (gPendingSaveCount == 0) {
                    publishDraft();
                }
            }
        },
        error: function() {
            gPublishing = false;
        }
    });
}


/*
 * An autocomplete() wrapper that converts our autocomplete data into the
 * format expected by jQuery.ui.autocomplete. It also adds some additional
 * explanatory text to the bottom of the autocomplete list.
 *
 * @param {string} fieldName  The field name ("groups" or "people").
 * @param {string} nameKey    The key containing the name in the result data.
 *
 * @return {jQuery} This jQuery set.
 */
$.fn.reviewsAutoComplete = function(fieldName, nameKey) {
    return this.each(function() {
        $(this)
            .autocomplete({
                formatItem: function(data) {
                    return data[nameKey];
                },
                matchCase: false,
                multiple: true,
                parse: function(data) {
                    var jsonData = eval("(" + data + ")");
                    var items = jsonData[fieldName];
                    var parsed = [];

                    for (var i = 0; i < items.length; i++) {
                        var value = items[i];

                        parsed.push({
                            data: value,
                            value: value[nameKey],
                            result: value[nameKey]
                        });
                    }

                    return parsed;
                },
                url: SITE_ROOT + "api/json/" + fieldName + "/"
            })
            .bind("autocompleteshow", function() {
                /*
                 * Add the footer to the bottom of the results pane the
                 * first time it's created.
                 */
                var resultsPane = $(".ui-autocomplete-results");

                if ($(".ui-autocomplete-footer", resultsPane).length == 0) {
                    $("<div/>")
                        .addClass("ui-autocomplete-footer")
                        .text("Press Tab to auto-complete.")
                        .appendTo(resultsPane);
                }
            });
    });
};


/*
 * Publishes the draft to the server. This assumes all fields have been
 * saved.
 *
 * Checks all the fields to make sure we have the information we need
 * and then redirects the user to the publish URL.
 */
function publishDraft() {
    if ($.trim($("#target_groups").html()) == "" &&
        $.trim($("#target_people").html()) == "") {
        alert("There must be at least one reviewer or group " +
	      "before this review request can be published.");
    } else if ($.trim($("#summary").html()) == "") {
        alert("The draft must have a summary.");
    } else if ($.trim($("#description").html()) == "") {
        alert("The draft must have a description.");
    } else {
        reviewRequestApiCall({
            path: "/publish/",
            buttons: gDraftBannerButtons,
            errorPrefix: "Publishing the draft has failed due to a " +
                         "server error:"
        });
    }
}


/*
 * Handles a comment section in a review.
 *
 * This will handle the "Add Comment" link and the draft banners for the
 * review.
 *
 * @param {string} review_id     The review ID.
 * @param {string} context_id    The comment section context ID.
 * @param {string} context_type  The comment section context type.
 *
 * @return {jQuery} This jQuery.
 */
$.fn.commentSection = function(review_id, context_id, context_type) {
    var self = $(this);
    var sectionId = context_id;
    var reviewEl = $("#review" + review_id);
    var commentsList = $(".reply-comments", self)
    var bannersEl = $(".banners", reviewEl);
    var bannerButtonsEl = $("input", bannersEl)

    var addCommentLink = $(".add_comment_link", self)
        .click(function() {
            createNewCommentForm();
            return false;
        });

    var yourcomments = $("pre[id^=yourcomment_]", self);

    if (yourcomments.length > 0) {
        createCommentEditor(yourcomments);
        showReplyDraftBanner(review_id);
        addCommentLink.hide();
    }

    /*
     * Creates a new comment form in response to the "Add Comment" link.
     */
    function createNewCommentForm() {
        var yourcomment_id = "yourcomment_" + sectionId + "-draft";
        $("<li/>")
            .addClass("reply-comment draft editor")
            .attr("id", yourcomment_id + "-item")
            .append($("<dl/>")
                .append($("<dt/>")
                    .append($("<label/>")
                        .attr("for", yourcomment_id)
                        .append($("<a/>")
                            .attr("href", gUserURL)
                            .text(gUserFullName)
                        )
                    )
                    .append('<dd><pre id="' + yourcomment_id + '"/></dd>')
                )
            )
            .appendTo(commentsList);

        var yourcommentEl = $("#" + yourcomment_id);
        createCommentEditor(yourcommentEl);
        yourcommentEl.inlineEditor("startEdit");

        addCommentLink.hide();
    }

    /*
     * Registers an inline editor for the comment form, handling setting the
     * comment on the server.
     *
     * @param {jQuery} els  The elements to create editors for.
     *
     * @return {jQuery} The provided elements.
     */
    function createCommentEditor(els) {
        return els.each(function() {
            var self = $(this);

            self
                .inlineEditor({
                    cls: "inline-comment-editor",
                    editIconPath: MEDIA_URL + "rb/images/edit.png?" +
                                  MEDIA_SERIAL,
                    notifyUnchangedCompletion: true,
                    multiline: true
                })
                .bind("complete", function(e, value) {
                    self.html(linkifyText(self.text()));
                    reviewRequestApiCall({
                        path: "/reviews/" + review_id + "/replies/draft/",
                        data: {
                            value:     value,
                            id:        context_id,
                            type:      context_type,
                            review_id: review_id
                        },
                        buttons: bannerButtonsEl,
                        success: function(rsp) {
                            removeCommentFormIfEmpty(self);
                            showReplyDraftBanner(review_id);
                        }
                    });
                })
                .bind("cancel", function(e) {
                    removeCommentFormIfEmpty(self);
                });
        });
    }

    /*
     * Removes a comment form if the contents are empty.
     *
     * @param {jQuery} editorEl  The inline editor element.
     */
    function removeCommentFormIfEmpty(editorEl) {
        var value = editorEl.inlineEditor("value");

        if (value.stripTags().strip() != "") {
            return;
        }

        $("#" + editorEl[0].id + "-item").hide("slow", function() {
            $(this).remove();

            if ($(".inline-comment-editor", reviewEl).length == 0) {
                bannersEl.children().remove();
            }

            addCommentLink.fadeIn();
        });
    }

    /*
     * Shows the reply draft banner on the review.
     *
     * @param {string} review_id  The review object's ID.
     */
    function showReplyDraftBanner(review_id) {
        if (bannersEl.children().length == 0) {
            bannersEl.append($("<div/>")
                .addClass("banner")
                .append("<h1>This reply is a draft</h1>")
                .append(" Be sure to publish when finished.")
                .append($('<input type="button"/>')
                    .val("Publish")
                    .click(function() {
                        reviewRequestApiCall({
                            path: '/reviews/' + review_id +
                                  '/replies/draft/save/',
                            buttons: bannerButtonsEl,
                            errorText: "Saving the reply draft has " +
                                       "failed due to a server error:"
                        });
                    })
                )
                .append($('<input type="button"/>')
                    .val("Discard")
                    .click(function() {
                        reviewRequestApiCall({
                            path: '/reviews/' + review_id +
                                  '/replies/draft/discard/',
                            buttons: bannerButtonsEl,
                            errorText: "Discarding the reply draft " +
                                       "has failed due to a server error:"
                        });
                    })
                )
            );
        }
    }
};


/*
 * Creates the comment detail dialog for lines in a diff. This handles the
 * maintenance of comment blocks and shows existing comments on a block.
 *
 * @return {jQuery} This jQuery.
 */
$.fn.commentDlg = function() {
    var SLIDE_DISTANCE = 10;
    var COMMENTS_BOX_WIDTH = 280;
    var FORM_BOX_WIDTH = 380;
    var self = this;

    /* State */
    var commentBlock = null;
    var textFieldWidthDiff = 0;
    var textFieldHeightDiff = 0;
    var dirty = false;
    var oldDirty = false;

    /* Page elements */
    var draftForm    = $("#draft-form", this);
    var commentsPane = $("#review_comments", this);
    var commentsList = $("#review_comment_list", this);
    var actionField  = $("#comment_action", draftForm);
    var buttons      = $(".buttons", draftForm);
    var statusField  = $(".status", draftForm);
    var cancelButton = $("#comment_cancel", draftForm)
        .click(function() {
            commentBlock.discardIfEmpty();
            self.close();
        });
    var deleteButton = $("#comment_delete", this)
        .click(function() {
            commentBlock.deleteComment();
            self.close();
        });
    var saveButton = $("#comment_save", this)
        .click(function() {
            commentBlock.setText(textField.val());
            commentBlock.save();
            self.close();
        });

    var textField    = $("#comment_text", draftForm)
        .keydown(function(e) { e.stopPropagation(); })
        .keypress(function(e) {
            e.stopPropagation();

            switch (e.keyCode) {
                case 10:
                case $.ui.keyCode.ENTER:
                    /* Enter */
                    if (e.ctrlKey) {
                        saveButton.click();
                    }
                    break;

                case $.ui.keyCode.ESCAPE:
                    /* Escape */
                    cancelButton.click();
                    break;

                default:
                    return;
            }
        })
        .keyup(function(e) {
            dirty = dirty || commentBlock.text != textField.val();

            if (dirty && !oldDirty) {
                saveButton.attr("disabled", textField.val() == "");
                statusField.html("This comment has unsaved changes.");
                self.handleResize();

                oldDirty = dirty;
            }

            e.stopPropagation();
        });

    this
        .css("position", "absolute")
        .mousedown(function(evt) {
            /*
             * Prevent this from reaching the selection area, which will
             * swallow the default action for the mouse down.
             */
            evt.stopPropagation();
        });

        if (!$.browser.msie || $.browser.version >= 8) {
            /*
             * resizable is pretty broken in IE 6/7.
             */
            this.resizable({
                handles: "all",
                transparent: true,
                resize: function() { self.handleResize(); }
            });
        }

        if (!$.browser.msie || $.browser.version >= 7) {
            /*
             * draggable works in IE7 and up, but not IE6.
             */
            this.draggable({
                handle: $(".title", this).css("cursor", "move")
            });
        }

    if (!LOGGED_IN) {
        textField.attr("disabled", true);
        saveButton.attr("disabled", true);
    }

    /*
     * Warn the user if they try to navigate away with unsaved comments.
     *
     * @param {event} evt The beforeunload event.
     *
     * @return {string} The dialog message (needed for IE).
     */
    window.onbeforeunload = function(evt) {
        if (dirty && self.is(":visible")) {
            if (!evt) {
                evt = window.event;
            }

            evt.returnValue = "You have unsaved changes that will be " +
                              "lost if you navigate away from this page.";
            return evt.returnValue;
        }
    };

    /*
     * Opens the comment dialog and focuses the text field.
     *
     * @return {jQuery} This jQuery.
     */
    this.open = function(fromEl) {
        this
            .css({
                top: parseInt(this.css("top")) - SLIDE_DISTANCE,
                opacity: 0
            })
            .show()
            .handleResize()
            .animate({
                top: "+=" + SLIDE_DISTANCE + "px",
                opacity: 1
            }, 350, "swing", function() {
                // Scroll the window so the box is on the screen if we need to.
                var offset = self.offset();
                var scrollTop = $(document).scrollTop();
                var topDiff = (scrollTop + $(window).height()) -
                              (offset.top + self.outerHeight(true));

                if (topDiff < 0) {
                    /* The box is off the screen. */
                    $(window).scrollTop(scrollTop - topDiff);
                }
            });

        textField.focus();

        oldDirty = false;
        dirty = false;

        return this;
    }

    /*
     * Closes the comment dialog, discarding the comment block if empty.
     *
     * @return {jQuery} This jQuery.
     */
    this.close = function() {
        if (self.is(":visible")) {
            textField.val("");
            self.animate({
                top: "-=" + SLIDE_DISTANCE + "px",
                opacity: 0
            }, 350, "swing", function() {
                self.hide();
                commentBlock = null;
                self.trigger("close");
            });
        } else {
            self.trigger("close");
        }

        return this;
    }

    /*
     * Sets the active comment block. This will reset the default state of
     * the comment dialog and update the UI to show any other comments in
     * the block.
     *
     * @param {CommentBlock} newCommentBlock The new comment block to set.
     *
     * @return {jQuery} This jQuery.
     */
    this.setCommentBlock = function(newCommentBlock) {
        if (commentBlock && commentBlock != newCommentBlock) {
            commentBlock.discardIfEmpty();
        }

        commentBlock = newCommentBlock;
        textField.val(commentBlock.text);
        dirty = false;

        /* Set the initial button states */
        deleteButton.setVisible(commentBlock.canDelete);
        saveButton.attr("disabled", true);

        /* Clear the status field. */
        statusField.empty();

        commentsList.empty();

        /*
         * Store the offsets of the text field so we can easily set
         * them relative to the dialog size when resizing.
         */
        commentsPane.hide();

        var showComments = false;

        if (commentBlock.comments.length > 0) {
            var odd = true;

            $(commentBlock.comments).each(function(i) {
                var item = $("<li/>")
                    .addClass(odd ? "odd" : "even");
                var header = $("<h2/>").appendTo(item).html(this.user.name);
                var actions = $('<span class="actions"/>')
                    .appendTo(header);
                $('<a href="' + this.url + '">View</a>').appendTo(actions);
                $('<a href="' + gReviewRequestPath +
                  '?reply_id=' + this.comment_id +
                  '&reply_type=' + commentBlock.type + '">Reply</a>')
                    .appendTo(actions);
                $("<pre/>").appendTo(item).text(this.text);

                item.appendTo(commentsList);

                showComments = true;

                odd = !odd;
            });
        }

        commentsPane.setVisible(showComments);

        /* Do this here so that calculations can be done before open() */
        var width = FORM_BOX_WIDTH;

        if (showComments) {
            width += COMMENTS_BOX_WIDTH;
        }

        /* Don't let the text field bump up the size we set below. */
        textField
            .width(10)
            .height(10);

        self
            .width(width)
            .height(250);

        return this;
    }

    /*
     * Handles the resize of the comment dialog. This will lay out the
     * elements in the dialog appropriately.
     */
    this.handleResize = function() {
        var width = self.width();
        var height = self.height();
        var formWidth = width - draftForm.getExtents("bp", "lr");
        var boxHeight = height;
        var commentsWidth = 0;

        if (commentsPane.is(":visible")) {
            commentsPane
                .width(COMMENTS_BOX_WIDTH - commentsPane.getExtents("bp", "lr"))
                .height(boxHeight - commentsPane.getExtents("bp", "tb"))
                .move(0, 0, "absolute");

            commentsList.height(commentsPane.height() -
                                commentsList.position().top -
                                commentsList.getExtents("bmp", "b"));

            commentsWidth = commentsPane.outerWidth(true);
            formWidth -= commentsWidth;
        }

        draftForm
            .width(formWidth)
            .height(boxHeight - draftForm.getExtents("bp", "tb"))
            .move(commentsWidth, 0, "absolute");

        var textFieldPos = textField.position();
        textField
            .width(draftForm.width() - textFieldPos.left -
                   textField.getExtents("bmp", "r"))
            .height(draftForm.height() - textFieldPos.top -
                    buttons.outerHeight(true) -
                    statusField.height() -
                    textField.getExtents("bmp", "b"));

        return this;
    }

    return this;
};


/*
 * Creates a review form for modifying a new review.
 *
 * This provides editing capabilities for creating or modifying a new
 * review. The list of comments are retrieved from the server, providing
 * context for the comments.
 *
 * @return {jQuery} The new review form element.
 */
$.reviewForm = function() {
    rbApiCall({
        type: "GET",
        dataType: "html",
        data: {},
        url: SITE_ROOT + "r/" + gReviewRequestId +
             "/reviews/draft/inline-form/",
        success: function(html) {
            createForm(html);
        }
    });

    var dlg;

    /*
     * Creates the actual review form. This is called once we have
     * the HTML for the form from the server.
     *
     * @param {string} formHTML  The HTML content for the form.
     */
    function createForm(formHTML) {
        dlg = $("<div/>")
            .attr("id", "review-form")
            .appendTo("body") // Needed for scripts embedded in the HTML
            .html(formHTML)
            .modalBox({
                title: "Review for: " + gReviewRequestSummary,
                stretchX: true,
                stretchY: true,
                buttons: [
                    $('<input type="button"/>')
                        .val("Publish Review")
                        .click(function(e) {
                            saveReview(true);
                            return false;
                        }),
                    $('<input type="button"/>')
                        .val("Discard Review")
                        .click(function(e) {
                            reviewAction("delete");
                        }),
                    $('<input type="button"/>')
                        .val("Cancel"),
                    $('<input type="button"/>')
                        .val("Save")
                        .click(function() {
                            saveReview();
                            return false;
                        })
                ]
            })
            .keypress(function(e) { e.stopPropagation(); })
            .trigger("ready");

        $(".body-top, .body-bottom", dlg)
            .inlineEditor({
                extraHeight: 50,
                forceOpen: true,
                multiline: true,
                notifyUnchangedCompletion: true,
                showButtons: false,
                showEditIcon: false
            });

        $("textarea:first", dlg).focus();
        dlg.attr("scrollTop", 0);

        loadDiffFragments("review_draft_diff_comments",
                          "review_draft_comment_container");
    }

    /*
     * Saves the review.
     *
     * This sets the shipit and body values, and saves all comments.
     */
    function saveReview(publish) {
        $.funcQueue("reviewForm").clear();

        $(".body-top, .body-bottom").inlineEditor("save");

        $(".comment-editable", dlg).each(function() {
            var editable = $(this);

            if (editable.inlineEditor("dirty")) {
                $.funcQueue("reviewForm").add(function() {
                    editable
                        .one("saved", $.funcQueue("reviewForm").next)
                        .inlineEditor("save");
              });
            }
        });

        $.funcQueue("reviewForm").add(function() {
            reviewAction(publish ? "publish" : "save",
                $.funcQueue("reviewForm").next,
                {
                    shipit: function() {
                        return $("#id_shipit", dlg)[0].checked ? 1 : 0;
                    },
                    body_top: function() {
                        return $(".body-top", dlg).text();
                    },
                    body_bottom: function() {
                        return $(".body-bottom", dlg).text();
                    }
                }
            );
        });

        $.funcQueue("reviewForm").add(function() {
            dlg.modalBox("destroy");

            if (publish) {
                hideReviewBanner();
                gReviewBanner.queue(function() {
                    window.location = gReviewRequestPath;
                });
            } else {
                showReviewBanner();
            }
        });

        $.funcQueue("reviewForm").start();
    }

    /*
     * Invokes a review action.
     *
     * @param {string}   action   The action.
     * @param {function} success  The optional success callback.
     * @param {object}   data     The optional data.
     */
    function reviewAction(action, success, data) {
        reviewRequestApiCall({
            path: getReviewDraftAPIPath() + "/" + action + "/",
            buttons: $("input", dlg),
            data: data,
            success: success
        });
    }
};


/*
 * Adds inline editing capabilities to a comment in the review form.
 *
 * options has the following fields:
 *
 *    path     - The relative API path.
 *    textKey  - The key in the data sent to the server containing the
 *               comment text.
 *    data     - The data sent to the server. Unless overridden, this has
 *               the field "action" set to "set".
 *
 * @param {object} options  The options, listed above.
 */
$.fn.reviewFormCommentEditor = function(options) {
    var self = this;

    options = $.extend({
        path: "",
        textKey: "text",
        data: {
            action: "set"
        }
    }, options);

    return this
        .inlineEditor({
            extraHeight: 50,
            forceOpen: true,
            multiline: true,
            notifyUnchangedCompletion: true,
            showButtons: false,
            showEditIcon: false,
            useEditIconOnly: false
        })
        .bind("complete", function(e, value) {
            options.data[options.textKey] = value;

            reviewRequestApiCall({
                path: options.path,
                data: options.data,
                success: function() { self.trigger("saved"); }
            });
        });
};


/*
 * Shows the review banner.
 */
function showReviewBanner() {
    if (gReviewBanner.is(":hidden")) {
        gReviewBanner
            .slideDown()
            .find(".banner")
                .hide()
                .slideDown();
    }
}


/*
 * Hides the review banner.
 */
function hideReviewBanner() {
    gReviewBanner
        .slideUp()
        .find(".banner")
            .slideUp();
}


/*
 * Queues the load of a diff fragment from the server.
 *
 * This will be added to a list, which will fetch the comments in batches
 * based on file IDs.
 *
 * @param {string} queue_name  The name for this load queue.
 * @param {string} comment_id  The ID of the comment.
 * @param {string} key         The key for this request, using the
 *                             filediff and interfilediff.
 */
function queueLoadDiffFragment(queue_name, comment_id, key) {
    if (!gPendingDiffFragments[queue_name]) {
        gPendingDiffFragments[queue_name] = {};
    }

    if (!gPendingDiffFragments[queue_name][key]) {
        gPendingDiffFragments[queue_name][key] = [];
    }

    gPendingDiffFragments[queue_name][key].push(comment_id);
}


/*
 * Begins the loading of all diff fragments on the page belonging to
 * the specified queue and storing in containers with the specified
 * prefix.
 */
function loadDiffFragments(queue_name, container_prefix) {
    if (!gPendingDiffFragments[queue_name]) {
        return;
    }

    for (var key in gPendingDiffFragments[queue_name]) {
        var comments = gPendingDiffFragments[queue_name][key];
        var url = gReviewRequestPath + "fragments/diff-comments/";

        for (var i = 0; i < comments.length; i++) {
            url += comments[i];

            if (i != comments.length - 1) {
                url += ","
            }
        }

        url += "/?queue=" + queue_name +
               "&container_prefix=" + container_prefix +
               "&" + AJAX_SERIAL;

        $.funcQueue("diff_comments").add(function(url) {
            var e = document.createElement("script");
            e.type = "text/javascript";
            e.src = url;
            document.body.appendChild(e);
        }(url));
    }

    // Clear the list.
    gPendingDiffFragments[queue_name] = {};

    $.funcQueue(queue_name).start();
}

$(document).ready(function() {
    /* Provide support for expanding submenus in the action list. */
    var menuitem = null;

    $("#actions > li").hover(function() {
        if (menuitem) {
            $("ul", menuitem).fadeOut("fast");
            menuitem = null;
        }

        $("ul", this).fadeIn("fast");
    }, function() {
        menuitem = $(this);
        setTimeout(function() {
            if (menuitem) {
                $("ul", menuitem).fadeOut("fast");
            }
        }, 400);
    });

    $("#btn-draft-publish").click(function() {
        /* Save all the fields if we need to. */
        gPublishing = true;
        var fields = $(".editable:inlineEditorDirty");
        gPendingSaveCount = fields.length;

        if (gPendingSaveCount == 0) {
            publishDraft();
        } else {
            fields.inlineEditor("save");
        }

        return false;
    });

    $("#btn-draft-discard").click(function() {
        reviewRequestApiCall({
            path: "/draft/discard/",
            buttons: gDraftBannerButtons,
            errorPrefix: "Reverting the draft has failed due to a " +
                         "server error:"
        });

        return false;
    });

    $("#btn-review-request-discard, #discard-review-request-link")
        .click(function() {
            reviewRequestApiCall({
                path: "/close/discarded/",
                buttons: gDraftBannerButtons,
                errorPrefix: "Discarding the review request has failed " +
                             "due to a server error:"
            });

            return false;
        });

    $("#link-review-request-close-submitted").click(function() {
        /*
         * This is a non-destructive event, so don't confirm unless there's
         * a draft. (TODO)
         */
        reviewRequestApiCall({
            path: "/close/submitted/",
            buttons: gDraftBannerButtons,
            errorPrefix: "Setting the review request as submitted has failed " +
                         "due to a server error:"
        });

        return false;
    });

    $("#btn-review-request-reopen").click(function() {
        reviewRequestApiCall({
            path: "/reopen/",
            buttons: gDraftBannerButtons,
            errorPrefix: "Reopening the review request has failed " +
                         "due to a server error:"
        });

        return false;
    });

    $("#delete-review-request-link").click(function() {
        var dlg = $("<p/>")
            .text("This deletion cannot be undone. All diffs and reviews " +
                  "will be deleted as well.")
            .modalBox({
                title: "Are you sure you want to delete this review request?",
                buttons: [
                    $('<input type="button" value="Cancel"/>'),
                    $('<input type="button" value="Delete"/>')
                        .click(function(e) {
                            reviewRequestApiCall({
                                path: "/delete/",
                                buttons: gDraftBannerButtons.add(
                                         $("input", dlg.modalBox("buttons"))),
                                errorPrefix: "Deleting the review request " +
                                             "has failed due to a server " +
                                             "error:",
                                success: function() {
                                    window.location = SITE_ROOT;
                                }
                            });
                        })
                ]
            });

        return false;
    });

    /* Edit Review buttons. */
    $("#review-link, #review-banner-edit").click(function() {
        $.reviewForm();
    });

    /* Review banner's Publish button. */
    $("#review-banner-publish").click(function() {
        reviewRequestApiCall({
            path: getReviewDraftAPIPath() + "/publish/",
            buttons: $("input", gReviewBanner),
            success: function() {
                hideReviewBanner();
                gReviewBanner.queue(function() {
                    window.location = gReviewRequestPath;
                });
            }
        });
    });

    /* Review banner's Delete button. */
    $("#review-banner-discard").click(function() {
        var dlg = $("<p/>")
            .text("If you discard this review, all related comments will " +
                  "be permanently deleted.")
            .modalBox({
                title: "Are you sure you want to discard this review?",
                buttons: [
                    $('<input type="button" value="Cancel"/>'),
                    $('<input type="button" value="Discard"/>')
                        .click(function(e) {
                            reviewRequestApiCall({
                                path: getReviewDraftAPIPath() + "/delete/",
                                buttons: $("input", gReviewBanner),
                                success: function() {
                                    hideReviewBanner();
                                    gReviewBanner.queue(function() {
                                        window.location = gReviewRequestPath;
                                    });
                                }
                            });
                        })
                ]
            });
    });

    if (gUserAuthenticated) {
        if (window["gEditable"]) {
            $(".editable").each(function() {
                var editable = $(this);

                editable
                    .inlineEditor({
                        cls: this.id + "-editor",
                        editIconPath: MEDIA_URL + "rb/images/edit.png?" +
                                      MEDIA_SERIAL,
                        multiline: this.tagName == "PRE",
                        showButtons:
                            !$(editable).hasClass("screenshot-editable"),
                        startOpen: this.id == "changedescription",
                        useEditIconOnly: $(editable).hasClass("comma-editable")
                    })
                    .bind("complete", function(e, value) {
                        setDraftField(editable[0].id, value);
                    });
            });

            var description = $("#description");
            var testing_done = $("#testing_done");

            if (description.length > 0) {
                description.html(linkifyText(description.text()));
                testing_done.html(linkifyText(testing_done.text()));
            }

            var targetGroupsEl = $("#target_groups");
            var targetPeopleEl = $("#target_people");

            if (targetGroupsEl.length > 0) {
                targetGroupsEl
                    .inlineEditor("field")
                    .reviewsAutoComplete("groups", "name");
            }

            if (targetPeopleEl.length > 0) {
                targetPeopleEl
                    .inlineEditor("field")
                    .reviewsAutoComplete("users", "username");
            }
        }

        $("pre.reviewtext").each(function() {
            $(this).html(linkifyText($(this).text()));
        });
    }

    loadDiffFragments("diff_fragments", "comment_container");
});

// vim: set et:sw=4:

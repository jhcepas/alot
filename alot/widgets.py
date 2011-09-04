"""
This file is part of alot.

Alot is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the
Free Software Foundation, either version 3 of the License, or (at your
option) any later version.

Notmuch is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
for more details.

You should have received a copy of the GNU General Public License
along with notmuch.  If not, see <http://www.gnu.org/licenses/>.

Copyright (C) 2011 Patrick Totzke <patricktotzke@gmail.com>
"""
import email
import urwid
from urwid.command_map import command_map
import logging
from collections import deque
from string import strip 

from settings import config
from helper import shorten
from helper import pretty_datetime
import message

def parse_authors(authors_string, maxlength):
    """ parse all authors in a string (comma separated) and adjust the
    best way to display them in a fixed length. 

    If the list of complete sender names does not fit in the
    max_length, it tries to shorten names by using only the first part
    of the name.

    If the list is still too long, hide authors according to the
    following priority:

      - First author is always shown (if too long is shorten with ellipsis)

      - If remaining space, last author is also shown (if too long,
        uses ellipsis)

      - If there are more than 2 authors in the thread, show the
        maximum of them. More recent senders have more priority (is
        the list of authors already sorted by the date of msgs????)
      
      - If it is necessary to hide authors, this is indicated with an
        ellipsis between the first and the other authors shown.

    Example (authors string with different length constrains):
         'King Kong, Mucho Muchacho, Jaime Huerta, Flash Gordon'
         'King, Mucho, Jaime, Flash'
         'King, ., Jaime, Flash'
         'King, ., J., Flash'
         'King, ., Flash'
         'King, ., Fl.'
         'King, .'
         'K., .' 
         'K.'
"""

    # I will create a list of authors by parsing author_string. I use
    # deque to do popleft without performance penalties
    authors = deque()

    # If author list is too long, it uses only the first part of each
    # name (gmail style)
    short_names = len(authors_string) > maxlength
    for au in authors_string.split(","):
        if short_names:
            authors.append(strip(au.split()[0]))
        else:
            authors.append(au)

    # Author chain will contain the list of author strings to be
    # concatenated using commas for the final formatted author_string.
    authors_chain = deque()

    # reserve space for first author
    first_au = shorten(authors.popleft(), maxlength)
    remaining_length = maxlength - len(first_au)

    # Tries to add an ellipsis if no space to show more than 1 author
    if authors and maxlength>3 and remaining_length < 3: 
        first_au = shorten(first_au, maxlength - 3)
        remaining_length += 3

    # Tries to add as more authors as possible. It takes into account
    # that if any author will be hidden, and ellipsis should be added
    while authors and remaining_length >= 3: 
        au = authors.pop()
        if len(au)>1 and (remaining_length == 3 or (authors and remaining_length <7)): 
            authors_chain.appendleft(u'\u2026')
            break 
        else:
            if authors:
                # 5= ellipsis + 2 x comma and space used as separators
                au_string = shorten(au, remaining_length - 5)
            else:
                # 2 = comma and space used as separator
                au_string = shorten(au, remaining_length - 2)
            remaining_length -= len(au_string) + 2
            authors_chain.appendleft(au_string)

    # Add the first author to the list and concatenate list 
    authors_chain.appendleft(first_au)
    authorsstring = ', '.join(authors_chain)
    return authorsstring

class ThreadlineWidget(urwid.AttrMap):
    def __init__(self, tid, dbman):
        self.dbman = dbman
        self.thread = dbman.get_thread(tid)
        self.tag_widgets = []
        self.display_content = config.getboolean('general',
                                    'display_content_in_threadline')
        self.rebuild()
        urwid.AttrMap.__init__(self, self.columns,
                               'threadline', 'threadline_focus')

    def rebuild(self):
        cols = []
        # DATE
        formatstring = config.get('general', 'timestamp_format')
        newest = self.thread.get_newest_date()
        if formatstring:
            datestring = newest.strftime(formatstring)
        else:
            datestring = pretty_datetime(newest).rjust(10)
        self.date_w = urwid.AttrMap(urwid.Text(datestring), 'threadline_date')

        # SIZE
        thread_size = self.thread.get_total_messages()
        # Show number of messages only if there are at least 2 mails
        # (save space in the line)
        if thread_size>1 and thread_size<=20:
            charcode = 0x2474 + thread_size
            mailcountstring = unichr(charcode)
        elif thread_size>1 and thread_size>20: 
            mailcountstring = "(%d)" % thread_size
        else:
            mailcountstring = " "

        # TAGS
        tags = self.thread.get_tags()
        tags.sort()
        tagstrings = []
        for tag in tags:
            tw = TagWidget(tag)
            self.tag_widgets.append(tw)
            tagstrings.append(('fixed', tw.width(), tw))
            
        # AUTHORS
        # for j in xrange(1, 30):
        #     print "DEBUG", j
        #     authorsstring = parse_authors(authors_string, j)
        authors_string = self.thread.get_authors() or '(None)'
        maxlength = config.getint('general', 'authors_maxlength')

        authorsstring = parse_authors(authors_string, maxlength - len(mailcountstring))
        offset = maxlength - len(authorsstring)
        mailcountstring = mailcountstring.rjust(offset)
        self.mailcount_w = urwid.AttrMap(urwid.Text(mailcountstring),
                                   'threadline_mailcount')

        self.authors_w = urwid.AttrMap(urwid.Text(authorsstring),
                                       'threadline_authors')

        # SUBJECT
        subjectstring = self.thread.get_subject().strip()
        self.subject_w = urwid.AttrMap(urwid.Text(subjectstring, wrap='clip'),
                                 'threadline_subject')

        # BODY
        if self.display_content:
            msgs = self.thread.get_messages().keys()
            msgs.sort()
            lastcontent = ' '.join([m.get_text_content() for m in msgs])
            contentstring = lastcontent.replace('\n', ' ').strip()
            self.content_w = urwid.AttrMap(urwid.Text(contentstring,
                                                      wrap='clip'),
                                           'threadline_content')

        # Set column order
        #self.select = urwid.AttrMap(urwid.Text("[ ] ", wrap='clip'),
        #                            'threadline_subject')
        #cols.append(('fixed', 4, self.select))
        cols.append(('fixed', len(datestring), self.date_w))
        cols.append(('fixed', len(authorsstring), self.authors_w))
        cols.append(('fixed', len(mailcountstring), self.mailcount_w))
        cols.extend(tagstrings)

        if subjectstring:
            cols.append(('fixed', len(subjectstring), self.subject_w))
        if self.display_content:
            cols.append(self.content_w)


        

        self.columns = urwid.Columns(cols, dividechars=1)
        self.original_widget = self.columns

    def render(self, size, focus=False):
        if focus:
            self.date_w.set_attr_map({None: 'threadline_date_focus'})
            self.mailcount_w.set_attr_map({None:
                                           'threadline_mailcount_focus'})
            for tw in self.tag_widgets:
                tw.set_focussed()
            self.authors_w.set_attr_map({None: 'threadline_authors_focus'})
            self.subject_w.set_attr_map({None: 'threadline_subject_focus'})
            if self.display_content:
                self.content_w.set_attr_map({None: 'threadline_content_focus'})
        else:
            self.date_w.set_attr_map({None: 'threadline_date'})
            self.mailcount_w.set_attr_map({None: 'threadline_mailcount'})
            for tw in self.tag_widgets:
                tw.set_unfocussed()
            self.authors_w.set_attr_map({None: 'threadline_authors'})
            self.subject_w.set_attr_map({None: 'threadline_subject'})
            if self.display_content:
                self.content_w.set_attr_map({None: 'threadline_content'})
        return urwid.AttrMap.render(self, size, focus)

    def selectable(self):
        return True

    def keypress(self, size, key):
        return key

    def get_thread(self):
        return self.thread


class BufferlineWidget(urwid.Text):
    def __init__(self, buffer):
        self.buffer = buffer
        line = '[' + buffer.typename + '] ' + unicode(buffer)
        urwid.Text.__init__(self, line, wrap='clip')

    def selectable(self):
        return True

    def keypress(self, size, key):
        return key

    def get_buffer(self):
        return self.buffer


class TagWidget(urwid.AttrMap):
    def __init__(self, tag):

        self.tag = tag
        #self.translated = config.get('tag-translate', tag, fallback=tag)
        #self.translated = self.translated.encode('utf-8')
        #self.txt = urwid.Text(self.translated, wrap='clip')
        #normal = config.get_tagattr(tag)

        # I understand yet the use of self.translated
        # Check if a symbol conversion and custom color exists for this tag
        normal, text = config.get('tag-colors', tag, []) or \
            [config.get_tagattr(tag), tag]
        focus = config.get_tagattr(tag, focus=True)
        self.txt = urwid.Text(text.encode('utf-8'), wrap='clip')
        self.focus_palette = focus
        self.unfocus_palette = normal
        urwid.AttrMap.__init__(self, self.txt, "message_attachment", focus)


    def width(self):
        # evil voodoo hotfix for double width chars that may
        # lead e.g. to strings with length 1 that need width 2
        return self.txt.pack()[0]

    def selectable(self):
        return True

    def keypress(self, size, key):
        return key

    def get_tag(self):
        return self.tag

    def set_focussed(self):
        #self.set_attr_map({None: config.get_tagattr(self.tag, focus=True)})
        self.set_attr_map({None: self.focus_palette})
    def set_unfocussed(self):
        #self.set_attr_map({None: config.get_tagattr(self.tag)})
        self.set_attr_map({None: self.unfocus_palette})

class CompleteEdit(urwid.Edit):
    def __init__(self, completer, edit_text=u'', **kwargs):
        self.completer = completer
        if not isinstance(edit_text, unicode):
            edit_text = unicode(edit_text, errors='replace')
        self.start_completion_pos = len(edit_text)
        self.completion_results = None
        urwid.Edit.__init__(self, edit_text=edit_text, **kwargs)

    def keypress(self, size, key):
        cmd = command_map[key]
        if cmd in ['next selectable', 'prev selectable']:
            pos = self.start_completion_pos
            original = self.edit_text[:pos]
            if not self.completion_results:  # not in completion mode
                self.completion_results = [''] + \
                    self.completer.complete(original)
                self.focus_in_clist = 1
            else:
                if cmd == 'next selectable':
                    self.focus_in_clist += 1
                else:
                    self.focus_in_clist -= 1
            if len(self.completion_results) > 1:
                suffix = self.completion_results[self.focus_in_clist %
                                          len(self.completion_results)]
                self.set_edit_text(original + suffix)
                self.edit_pos += len(suffix)
            else:
                self.set_edit_text(original + ' ')
                self.edit_pos += 1
                self.start_completion_pos = self.edit_pos
                self.completion_results = None
        else:
            result = urwid.Edit.keypress(self, size, key)
            self.start_completion_pos = self.edit_pos
            self.completion_results = None
            return result


class MessageWidget(urwid.WidgetWrap):
    """flow widget that displays a single message"""
    #TODO: atm this is heavily bend to work nicely with ThreadBuffer to display
    #a tree structure. A better way would be to keep this widget simple
    #(subclass urwid.Pile) and use urwids new Tree widgets
    def __init__(self, message, even=False, folded=True, depth=0, bars_at=[]):
        """
        :param message: the message to display
        :type message: alot.db.Message
        :param even: use messagesummary_even theme for summary
        :type even: boolean
        :param unfolded: unfold message initially
        :type unfolded: boolean
        :param depth: number of characters to shift content to the right
        :type depth: int
        :param bars_at: list of positions smaller than depth where horizontal
                        ars are used instead of spaces.
        :type bars_at: list(int)
        """
        self.message = message
        self.depth = depth
        self.bars_at = bars_at
        self.even = even
        self.folded = folded

        # build the summary line, header and body will be created on demand
        self.sumline = self._build_sum_line()
        self.headerw = None
        self.attachmentw = None
        self.bodyw = None
        self.displayed_list = [self.sumline]
        #build pile and call super constructor
        self.pile = urwid.Pile(self.displayed_list)
        urwid.WidgetWrap.__init__(self, self.pile)
        #unfold if requested
        if not folded:
            self.fold(visible=True)

    def get_focus(self):
        return self.pile.get_focus()

    #TODO re-read tags
    def rebuild(self):
        self.pile = urwid.Pile(self.displayed_list)
        self._w = self.pile

    def _build_sum_line(self):
        """creates/returns the widget that displays the summary line."""
        self.sumw = MessageSummaryWidget(self.message, even=self.even)
        cols = []
        bc = list()  # box_columns
        if self.depth > 1:
            bc.append(0)
            cols.append(self._get_spacer(self.bars_at[1:-1]))
        if self.depth > 0:
            if self.bars_at[-1]:
                arrowhead = u'\u251c\u25b6'
            else:
                arrowhead = u'\u2514\u25b6'
            cols.append(('fixed', 2, urwid.Text(arrowhead)))
        cols.append(self.sumw)
        line = urwid.Columns(cols, box_columns=bc)
        return line

    def _get_header_widget(self):
        """creates/returns the widget that displays the mail header"""
        if not self.headerw:
            displayed = config.getstringlist('general', 'displayed_headers')
            cols = [MessageHeaderWidget(self.message.get_email(), displayed)]
            bc = list()
            if self.depth:
                cols.insert(0, self._get_spacer(self.bars_at[1:]))
                bc.append(0)
            self.headerw = urwid.Columns(cols, box_columns=bc)
        return self.headerw

    def _get_attachment_widget(self):
        if self.message.get_attachments() and not self.attachmentw:
            lines = []
            for a in self.message.get_attachments():
                cols = [AttachmentWidget(a)]
                bc = list()
                if self.depth:
                    cols.insert(0, self._get_spacer(self.bars_at[1:]))
                    bc.append(0)
                lines.append(urwid.Columns(cols, box_columns=bc))
            self.attachmentw = urwid.Pile(lines)
        return self.attachmentw

        attachments = message.get_attachments()

    def _get_body_widget(self):
        """creates/returns the widget that displays the mail body"""
        if not self.bodyw:
            cols = [MessageBodyWidget(self.message.get_email())]
            bc = list()
            if self.depth:
                cols.insert(0, self._get_spacer(self.bars_at[1:]))
                bc.append(0)
            self.bodyw = urwid.Columns(cols, box_columns=bc)
        return self.bodyw

    def _get_spacer(self, bars_at):
        prefixchars = []
        length = len(bars_at)
        for b in bars_at:
            if b:
                c = u'\u2502'
            else:
                c = ' '
            prefixchars.append(('fixed', 1, urwid.SolidFill(c)))

        spacer = urwid.Columns(prefixchars, box_columns=range(length))
        return ('fixed', length, spacer)

    def toggle_full_header(self):
        """toggles if message headers are shown"""
        # caution: this is very ugly, it's supposed to get the headerwidget.
        col = self._get_header_widget().widget_list
        hws = [h for h in col if isinstance(h, MessageHeaderWidget)][0]
        hws.toggle_all()

    def fold(self, visible=False):
        hw = self._get_header_widget()
        aw = self._get_attachment_widget()
        bw = self._get_body_widget()
        if visible:
            if self.folded:  # only if not already unfolded
                self.displayed_list.append(hw)
                if aw:
                    self.displayed_list.append(aw)
                self.displayed_list.append(bw)
                self.folded = False
                self.rebuild()
        else:
            if not self.folded:
                self.displayed_list.remove(hw)
                if aw:
                    self.displayed_list.remove(aw)
                self.displayed_list.remove(bw)
                self.folded = True
                self.rebuild()

    def selectable(self):
        return True

    def keypress(self, size, key):
        return self.pile.keypress(size, key)

    def get_message(self):
        """get contained message
        returns: alot.db.Message"""
        return self.message

    def get_email(self):
        """get contained email
        returns: email.Message"""
        return self.message.get_email()


class MessageSummaryWidget(urwid.WidgetWrap):
    """a one line summary of a message"""

    def __init__(self, message, even=True):
        """
        :param message: the message to summarize
        :type message: alot.db.Message
        """
        self.message = message
        self.even = even
        if even:
            attr = 'messagesummary_even'
        else:
            attr = 'messagesummary_odd'
        sumstr = self.__str__()
        txt = urwid.AttrMap(urwid.Text(sumstr), attr, 'messagesummary_focus')
        urwid.WidgetWrap.__init__(self, txt)

    def __str__(self):
        return self.message.__str__()

    def selectable(self):
        return True

    def keypress(self, size, key):
        return key


class MessageHeaderWidget(urwid.AttrMap):
    """
    displays a "key:value\n" list of email headers.
    RFC 2822 style encoded values are decoded into utf8 first.
    """

    def __init__(self, eml, displayed_headers=None):
        """
        :param eml: the email
        :type eml: email.Message
        :param displayed_headers: a whitelist of header fields to display
        :type state: list(str)
        """
        self.eml = eml
        self.display_all = False
        self.displayed_headers = displayed_headers
        headerlines = self._build_lines(displayed_headers)
        urwid.AttrMap.__init__(self, urwid.Pile(headerlines), 'message_header')

    def toggle_all(self):
        if self.display_all:
            self.display_all = False
            headerlines = self._build_lines(self.displayed_headers)
        else:
            self.display_all = True
            headerlines = self._build_lines(None)
        logging.info('all : %s' % headerlines)
        self.original_widget = urwid.Pile(headerlines)

    def _build_lines(self, displayed):
        max_key_len = 1
        headerlines = []
        if not displayed:
            displayed = self.eml.keys()
        for key in displayed:
            if key in self.eml:
                if len(key) > max_key_len:
                    max_key_len = len(key)
        for key in displayed:
            #todo: parse from,cc,bcc seperately into name-addr-widgets
            if key in self.eml:
                valuelist = email.header.decode_header(self.eml[key])
                value = ''
                for v, enc in valuelist:
                    if enc:
                        value = value + v.decode(enc)
                    else:
                        value = value + v
                #sanitize it a bit:
                value = value.replace('\t', ' ')
                value = ' '.join([line.strip() for line in value.splitlines()])
                keyw = ('fixed', max_key_len + 1,
                        urwid.Text(('message_header_key', key)))
                valuew = urwid.Text(('message_header_value', value))
                line = urwid.Columns([keyw, valuew])
                headerlines.append(line)
        return headerlines


class MessageBodyWidget(urwid.AttrMap):
    """displays printable parts of an email"""

    def __init__(self, msg):
        bodytxt = message.extract_body(msg)
        urwid.AttrMap.__init__(self, urwid.Text(bodytxt), 'message_body')


class AttachmentWidget(urwid.WidgetWrap):
    def __init__(self, attachment, selectable=True):
        self._selectable = selectable
        self.attachment = attachment
        if not isinstance(attachment, message.Attachment):
            self.attachment = message.Attachment(self.attachment)
        widget = urwid.AttrMap(urwid.Text(unicode(self.attachment)),
                               'message_attachment',
                               'message_attachment_focussed')
        urwid.WidgetWrap.__init__(self, widget)

    def get_attachment(self):
        return self.attachment

    def selectable(self):
        return self._selectable

    def keypress(self, size, key):
        return key

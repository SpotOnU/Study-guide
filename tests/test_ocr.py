from studyguide.ocr import TextBox, order_lines


def test_lines_are_put_in_reading_order():
    boxes = [
        TextBox("third line", 0.1, 0.60, 0.05),
        TextBox("Title", 0.1, 0.05, 0.08),
        TextBox("right half", 0.55, 0.301, 0.05),
        TextBox("left half", 0.1, 0.30, 0.05),
    ]
    assert order_lines(boxes) == "Title\nleft half right half\nthird line"


def test_empty_input():
    assert order_lines([]) == ""

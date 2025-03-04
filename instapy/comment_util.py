# -*- coding: utf-8 -*-
""" Module which handles the commenting features """
# import built-in & third-party modules
import random
import emoji

# import InstaPy modules
from .time_util import sleep
from .util import update_activity
from .util import add_user_to_blacklist
from .util import click_element
from .util import get_action_delay
from .util import explicit_wait
from .util import web_address_navigator
from .util import evaluate_mandatory_words
from .event import Event
from .quota_supervisor import quota_supervisor
from .xpath import read_xpath

# import exceptions
from selenium.common.exceptions import WebDriverException
from selenium.common.exceptions import InvalidElementStateException
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys


def get_comment_input(browser):
    comment_input = browser.find_elements_by_xpath(
        read_xpath(get_comment_input.__name__, "comment_input")
    )

    if len(comment_input) <= 0:
        comment_input = browser.find_elements_by_xpath(
            read_xpath(get_comment_input.__name__, "placeholder")
        )

    return comment_input


def open_comment_section(browser, logger):
    missing_comment_elem_warning = (
        "--> Comment Button Not Found!"
        "\t~may cause issues with browser windows of smaller widths"
    )

    comment_elem = browser.find_elements_by_xpath(
        read_xpath(open_comment_section.__name__, "comment_elem")
    )

    if len(comment_elem) > 0:
        try:
            click_element(browser, comment_elem[0])

        except WebDriverException:
            logger.warning(missing_comment_elem_warning)

    else:
        logger.warning(missing_comment_elem_warning)


def comment_image(browser, username, comments, blacklist, logger, logfolder, index=0):
    """Checks if it should comment on the image"""
    # check action availability
    if quota_supervisor("comments") == "jump":
        return False, "jumped"

    rand_comment = random.choice(comments).format(username)
    rand_comment = emoji.demojize(rand_comment)
    rand_comment = emoji.emojize(rand_comment, use_aliases=True)
    if index == 0:
        open_comment_section(browser, logger)
        # wait, to avoid crash
        sleep(3+random.uniform(0,1))
    comment_input = get_comment_input(browser)

    try:
        if len(comment_input) > 0:
            # wait, to avoid crash
            sleep(2+random.uniform(0,1))
            comment_input = get_comment_input(browser)
            # below, an extra space is added to force
            # the input box to update the reactJS core
            comment_to_be_sent = rand_comment

            # wait, to avoid crash
            sleep(2+random.uniform(0,1))
            # click on textarea/comment box and enter comment
            (
                ActionChains(browser)
                .move_to_element(comment_input[0])
                .click()
                .send_keys(comment_to_be_sent)
                .perform()
            )
            # wait, to avoid crash
            sleep(2+random.uniform(0,1))
            # post comment / <enter>
            (
                ActionChains(browser)
                .move_to_element(comment_input[0])
                .send_keys(Keys.ENTER)
                .perform()
            )

            update_activity(
                browser,
                action="comments",
                state=None,
                logfolder=logfolder,
                logger=logger,
            )

            if blacklist["enabled"] is True:
                action = "commented"
                add_user_to_blacklist(
                    username, blacklist["campaign"], action, logger, logfolder
                )
        else:
            logger.warning(
                "--> Comment Action Likely Failed!" "\t~comment Element was not found"
            )
            return False, "commenting disabled"

    except InvalidElementStateException:
        logger.warning(
            "--> Comment Action Likely Failed!"
            "\t~encountered `InvalidElementStateException` :/"
        )
        return False, "invalid element state"
    except WebDriverException as ex:
        logger.error(ex)

    logger.info("--> Commented: {}".format(rand_comment.encode("utf-8")))
    Event().commented(username)

    # get the post-comment delay time to sleep
    naply = get_action_delay("comment")
    sleep(naply)

    return True, "success"


def verify_commenting(browser, maximum, minimum, logger):
    """
     Get the amount of existing existing comments and
    compare it against maximum & minimum values defined by user
    """

    commenting_state, msg = is_commenting_enabled(browser, logger)
    if commenting_state is not True:
        disapproval_reason = "--> Not commenting! {}".format(msg)
        return False, disapproval_reason

    comments_count, msg = get_comments_count(browser, logger)
    if comments_count is None:
        disapproval_reason = "--> Not commenting! {}".format(msg)
        return False, disapproval_reason

    if maximum is not None and comments_count > maximum:
        disapproval_reason = "Not commented on this post! ~more comments exist off maximum limit at {}".format(
            comments_count
        )
        return False, disapproval_reason

    elif minimum is not None and comments_count < minimum:
        disapproval_reason = "Not commented on this post! ~less comments exist off minumum limit at {}".format(
            comments_count
        )
        return False, disapproval_reason

    return True, "Approval"


def verify_mandatory_words(
    mand_words,
    comments,
    browser,
    logger,
):
    if len(mand_words) > 0 or isinstance(comments[0], dict):
        try:
            post_desc = browser.execute_script(
                "return window.__additionalData[Object.keys(window.__additionalData)[0]].data."
                "graphql.shortcode_media."
                "edge_media_to_caption.edges[0]['node']['text']"
            ).lower()

        except Exception:
            post_desc = None

        try:
            first_comment = browser.execute_script(
                "return window.__additionalData[Object.keys(window.__additionalData)[0]].data."
                "graphql.shortcode_media."
                "edge_media_to_parent_comment.edges[0]['node']['text']"
            ).lower()

        except Exception:
            first_comment = None

        if post_desc is None and first_comment is None:
            return False, [], "couldn't get post description and comments"

        text = (
            post_desc
            if post_desc is not None
            else "" + " " + first_comment
            if first_comment is not None
            else ""
        )

        if len(mand_words) > 0:
            if not evaluate_mandatory_words(text, mand_words):
                return False, [], "mandatory words not in post desc"

        if isinstance(comments[0], dict):
            # The comments definition is a compound definition of conditions and comments
            for compund_comment in comments:
                if (
                    "mandatory_words" not in compund_comment
                    or evaluate_mandatory_words(
                        text, compund_comment["mandatory_words"]
                    )
                ):
                    return True, compund_comment["comments"], "Approval"
            return (
                False,
                [],
                "Coulnd't match the mandatory words in any comment definition",
            )

    return True, comments, "Approval"


def get_comments_on_post(
    browser, owner, poster, amount, post_link, ignore_users, randomize, logger
):
    """ Fetch comments data on posts """
    web_address_navigator(browser, post_link)

    comments = []
    commenters = []

    if randomize is True:
        amount = amount * 3

    # check if commenting on the post is enabled
    (commenting_approved, disapproval_reason,) = verify_commenting(
        browser,
        None,
        None,
        logger,
    )
    if not commenting_approved:
        logger.info(disapproval_reason)
        return None

    # get comments & commenters information path
    like_button_full_XPath = read_xpath(
        get_comments_on_post.__name__, "like_button_full_XPath"
    )
    unlike_button_full_XPath = read_xpath(
        get_comments_on_post.__name__, "unlike_button_full_XPath"
    )

    # wait for page fully load [IMPORTANT!]
    explicit_wait(browser, "PFL", [], logger, 10)

    try:
        all_comment_like_buttons = browser.find_elements_by_xpath(
            like_button_full_XPath
        )

        if all_comment_like_buttons:
            commenter = None
            comment = None

            data = browser.execute_script(
                "return window.__additionalData[Object.keys(window.__additionalData)].data."
                "graphql.shortcode_media.edge_media_to_parent_comment"
            )
            for value in data["edges"]:
                commenter = value["node"]["owner"]["username"]
                comment = value["node"]["text"]

                if (
                    commenter
                    and commenter not in commenters
                    and commenter not in [owner, poster, ignore_users]
                    and comment
                ):
                    commenters.append(commenter)
                    comments.append(comment)
                else:
                    logger.info("Could not grab any commenter from this post")

        else:
            comment_unlike_buttons = browser.find_elements_by_xpath(
                unlike_button_full_XPath
            )

            if comment_unlike_buttons:
                logger.info(
                    "Grabbed {} comment(s) on this post and already liked.".format(
                        len(comment_unlike_buttons)
                    )
                )
            else:
                logger.info("There are no any comments available on this post.")
            return None

    except NoSuchElementException:
        logger.info("Failed to grab comments on this post.")
        return None

    if not comments:
        logger.info("Could not grab any usable comments from this post...")
        return None

    else:
        comment_data = list(zip(commenters, comments))
        if randomize is True:
            random.shuffle(comment_data)

        logger.info(
            "Grabbed only {} usable comment(s) from this post...".format(
                len(comment_data)
            )
        )

        return comment_data


def is_commenting_enabled(browser, logger):
    """ Find out if commenting on the post is enabled """

    try:
        comments_disabled = browser.execute_script(
            "return window.__additionalData[Object.keys(window.__additionalData)[0]].data"
            ".graphql.shortcode_media.comments_disabled"
        )

    except WebDriverException:
        try:
            browser.execute_script("location.reload()")
            update_activity(browser, state=None)

            comments_disabled = browser.execute_script(
                "return window.__additionalData[Object.keys(window.__additionalData)[0]].data"
                ".graphql.shortcode_media.comments_disabled"
            )

        except Exception as e:
            msg = "Failed to check comments' status for verification!\n\t{}".format(
                str(e).encode("utf-8")
            )
            return False, msg

    if comments_disabled is True:
        msg = "Comments are disabled for this post."
        return False, msg

    return True, "Success"


def get_comments_count(browser, logger):
    """ Get the number of total comments in the post """
    try:
        comments_count = browser.execute_script(
            "return window.__additionalData[Object.keys(window.__additionalData)[0]].data"
            ".graphql.shortcode_media.edge_media_preview_comment.count"
        )

    except Exception as e:
        msg = "Failed to get comments' count!\n\t{}".format(str(e).encode("utf-8"))
        return None, msg

    return comments_count, "Success"


def verify_commented_image(browser, link, owner, logger):
    """ Fetch comments data on posts to determine if already commented """

    web_address_navigator(browser, link)

    # wait for page fully load [IMPORTANT!]
    explicit_wait(browser, "PFL", [], logger, 10)

    try:
        commenter = None
        comment = None
        data = browser.execute_script(
            "return window.__additionalData[Object.keys(window.__additionalData)].data."
            "graphql.shortcode_media.edge_media_to_parent_comment"
        )
        for value in data["edges"]:
            commenter = value["node"]["owner"]["username"]
            comment = value["node"]["text"]

            if commenter and commenter == owner:
                message = (
                    "--> The post has already been commented on before: '{}'".format(
                        comment
                    )
                )
                return True, message

    except NoSuchElementException:
        # Cannot be determined if the post has been comment by InstaPy user,
        # and then it will not be commented until next loop, maybe comments
        # on the post have been limited. Return True, to emulate or assume the
        # post has been commented by user.
        message = (
            "--> Failed to get comments on this post, will not comment the post..."
        )
        return True, message

    message = "--> Could not found owner's comment in this post, trying to comment..."
    return None, message


def process_comments(
    comments,
    clarifai_comments,
    delimit_commenting,
    max_comments,
    min_comments,
    comments_mandatory_words,
    owner,
    user_name,
    blacklist,
    browser,
    link,
    logger,
    logfolder,
    index,
    publish=True
):

    # comments
    if delimit_commenting:
        (commenting_approved, disapproval_reason,) = verify_commenting(
            browser,
            max_comments,
            min_comments,
            logger,
        )
        if not commenting_approved:
            logger.info(disapproval_reason)
            return False

    (
        commenting_approved,
        selected_comments,
        disapproval_reason,
    ) = verify_mandatory_words(
        comments_mandatory_words,
        comments,
        browser,
        logger,
    )

    if not commenting_approved:
        logger.info(disapproval_reason)
        return False

    if len(clarifai_comments) > 0:
        selected_comments = clarifai_comments

    # smart commenting
    if comments and publish:
        # trevtravtrev commented all of the following code that was disabling multi comment per post

        # # Check if InstaPy already commented on this post, it could be the
        # # case that the image has been liked (manually) but not commented, so
        # # we want to comment the post like usually we do.
        # commented_image, message = verify_commented_image(browser, link, owner, logger)
        #
        # if commented_image:
        #     # The post has already been commented, either manually or InstaPy
        #     # Commenting twice by InstaPy user is not allowd by now or could
        #     # not get comments on this post to check if InstaPy user commented
        #     # before, so will not comment until next check
        #     logger.info(message)
        #     return False
        # else:
        #     logger.info(message)

        comment_state, _ = comment_image(
            browser,
            user_name,
            selected_comments,
            blacklist,
            logger,
            logfolder,
            index
        )
        # commented out by trevtravtrev, don't return to user page so more comments can be posted.
        
        # # Return to the target uset page
        # user_link = "https://www.instagram.com/{}/".format(user_name)
        # web_address_navigator(browser, user_link)

        return comment_state

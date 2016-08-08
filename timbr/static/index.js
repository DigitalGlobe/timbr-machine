define(function() { return /******/ (function(modules) { // webpackBootstrap
/******/ 	// The module cache
/******/ 	var installedModules = {};

/******/ 	// The require function
/******/ 	function __webpack_require__(moduleId) {

/******/ 		// Check if module is in cache
/******/ 		if(installedModules[moduleId])
/******/ 			return installedModules[moduleId].exports;

/******/ 		// Create a new module (and put it into the cache)
/******/ 		var module = installedModules[moduleId] = {
/******/ 			exports: {},
/******/ 			id: moduleId,
/******/ 			loaded: false
/******/ 		};

/******/ 		// Execute the module function
/******/ 		modules[moduleId].call(module.exports, module, module.exports, __webpack_require__);

/******/ 		// Flag the module as loaded
/******/ 		module.loaded = true;

/******/ 		// Return the exports of the module
/******/ 		return module.exports;
/******/ 	}


/******/ 	// expose the modules object (__webpack_modules__)
/******/ 	__webpack_require__.m = modules;

/******/ 	// expose the module cache
/******/ 	__webpack_require__.c = installedModules;

/******/ 	// __webpack_public_path__
/******/ 	__webpack_require__.p = "";

/******/ 	// Load entry module and return exports
/******/ 	return __webpack_require__(0);
/******/ })
/************************************************************************/
/******/ ([
/* 0 */
/***/ function(module, exports, __webpack_require__) {

	"use strict";

	var _jupyterReactJs = __webpack_require__(1);

	var _jupyterReactJs2 = _interopRequireDefault(_jupyterReactJs);

	function _interopRequireDefault(obj) { return obj && obj.__esModule ? obj : { default: obj }; }

	if (window.require) {
	    window.require.config({
	        map: {
	            "*": {
	                "components": "/nbextensions/timbr_machine/components.js"
	            }
	        }
	    });
	}

	function load_ipython_extension() {
	    requirejs(["base/js/namespace", "base/js/events", "components"], function (Jupyter, events, components) {
	        __webpack_require__(6);
	        // initialize jupyter react cells, comm mananger and components
	        _jupyterReactJs2.default.init(Jupyter, events, 'timbr.machine', { components: components });
	    });
	}

	module.exports = {
	    load_ipython_extension: load_ipython_extension
	};

/***/ },
/* 1 */
/***/ function(module, exports, __webpack_require__) {

	if (window.require) {
	    window.require.config({
	        map: {
	            "*" : {
	                "react": "https://fb.me/react-15.2.1.min.js",
	                "react-dom": "https://fb.me/react-dom-15.2.1.min.js"
	            }
	        }
	    });
	}

	var Area = __webpack_require__(2);
	var Manager = __webpack_require__(3);
	var ReactComponent = __webpack_require__(4);

	var init = function( Jupyter, events, comm_target, component_options ) {

	    requirejs([ "react", "react-dom", "services/kernels/comm" ], function( React, ReactDom, Comm ) {
	        window.React = React;
	        window.ReactDom = ReactDom;
	    
	        /**
	         * handle_kernel 
	         * creates an instance of a "Manager" used to listen for new comms and create new components
	         */
	        var handle_kernel = function(Jupyter, kernel) {
	          if ( kernel.comm_manager && kernel.component_manager === undefined ) {
	            kernel.component_manager = new Manager.ComponentManager( kernel, Comm );
	          } 

	          if ( kernel.component_manager ) {
	            var Component = ReactComponent( component_options );
	            kernel.component_manager.register( comm_target, Component ) 
	          }
	        };

	        /**
	         *
	         */
	        // TODO need to handle clear out output calls
	        var handle_cell = function(cell) {
	            if ( cell.cell_type === 'code' ) {
	                if ( !cell.react_dom ) {
	                    cell.react_dom = new Area( cell );
	                } else if ( cell.react_dom.clear !== undefined ) {
	                    cell.react_dom.clear();
	                }
	            }
	        };

	        // On new kernel session create new comm managers
	        if (Jupyter.notebook && Jupyter.notebook.kernel) {
	            handle_kernel(Jupyter, Jupyter.notebook.kernel);
	        }
	        events.on('kernel_created.Kernel kernel_created.Session', function(event, data) {
	            handle_kernel(Jupyter, data.kernel);
	        });

	        // Create react component areas in cells
	        // Each cell in the notebook will have an area 
	        // that a component will render itself into
	        var cells = Jupyter.notebook.get_cells();
	        cells.forEach( cell => {
	            handle_cell( cell );
	        });

	        events.on( 'create.Cell', function( event, data ) {
	            handle_cell( data.cell );
	        });

	        events.on( 'delete.Cell', function( event, data ) {
	            if ( data.cell && data.cell.react_dom ) {
	                data.cell.react_dom.clear();
	            }
	        });
	    });

	};

	module.exports = {
	  Manager,
	  ReactComponent,
	  Area,
	  init
	};


/***/ },
/* 2 */
/***/ function(module, exports) {

	// TODO 
	// needs to bind to clear_display calls
	// add a "dispose" method that will will wipre all contents, call that on clear_display and cell delete etc.

	var Area = function( cell ) {
	    var area = document.createElement('div');
	    area.classList.add('jupyter-react-area');
	    area.classList.add('widget-area');
	    this.area = area;

	    var _prompt = document.createElement('div');
	    _prompt.classList.add('prompt');
	    area.appendChild(_prompt);

	    var subarea = document.createElement('div');
	    subarea.classList.add('jupyter-react-subarea');
	    subarea.classList.add('widget-subarea');
	    area.appendChild(subarea);

	    this.subarea = subarea;

	    if (cell.input) {
	        cell.input.after(area);
	    } else {
	        throw new Error('Cell does not have an `input` element.  Is it not a CodeCell?');
	    }
	};

	Area.prototype.clear = function(){ 
	    this.subarea.innerHTML = '';
	};



	module.exports = Area;


/***/ },
/* 3 */
/***/ function(module, exports) {

	function Manager( kernel, comm ) {
	  this.kernel = kernel;
	  this.comm = comm;
	  this.components = {};

	  this.register = function( target, Component ) {
	    var self = this;

	    // new targets...
	    if ( !this.components[ target ] ) {
	      this.components[ target ] = { Component: Component };
	      kernel.comm_manager.register_target( target, function ( comm, msg ) {
	        if ( msg[ 'msg_type' ] === 'comm_open' ) {
	          self.components[ target ][ comm.comm_id ] = self.components[ target ].Component( comm, msg );
	        }
	      });
	    }

	    // look for comms that need to be re-created (page refresh)
	    this.kernel.comm_info( target, function( info ) { 
	      var comms = Object.keys( info['content']['comms'] );
	      var md = Jupyter.notebook.metadata;
	      if ( comms.length ) {
	        comms.forEach( function( comm_id ) {
	          if ( md.react_comms && md.react_comms[ comm_id ] ) {
	            var cell = self._get_cell( md.react_comms[ comm_id ] );
	            if ( cell ) {
	              var module = comm_id.split( '.' ).slice( -1 )[ 0 ];
	              var newComm = self._create_comm( target, comm_id );
	              self.components[ target ][ newComm.comm_id ] = self.components[ target ].Component( 
	                newComm, 
	                { content: { data: { module: module } } }, 
	                cell 
	              )
	              self.components[ target ][ newComm.comm_id ].render();
	            }
	          }
	        });
	      }
	    })
	  };

	  this._get_cell = function( index ) {
	    return Jupyter.notebook.get_cells()[ parseInt(index) ];
	  }

	  this._create_comm = function( target, comm_id ) {
	    var newComm = new this.comm.Comm( target, comm_id );
	    Jupyter.notebook.kernel.comm_manager.register_comm( newComm );
	    return newComm;
	  }

	  return this;
	};

	module.exports = { 
	  ComponentManager: Manager 
	};


/***/ },
/* 4 */
/***/ function(module, exports, __webpack_require__) {

	/* WEBPACK VAR INJECTION */(function(module) {// Base component that handles comm messages and renders components to notebook cell

	module.exports = function Component( options ) {
	  return function (comm, props, cell) {
	    this.cell = cell;
	    this.comm = comm;
	    this.module = props.content.data.module;
	    this.domId = props.content.data.domId;

	    // Handle all messages over this comm
	    this.handleMsg = msg => {
	      console.log('MESSAGE', msg)
	      var data = msg.content.data;
	      switch (data.method) {
	        case "update":
	          if ( options.on_update ) {
	            return options.on_update(module, data.props);
	          }
	          // else re-render
	          this.renderComponent( msg, data.props );
	          break;
	        case "display":
	          // save comm id and cell id to notebook.metadata
	          this._saveComponent( msg );
	          break;
	      }
	    };

	    // save cell index to notebook metadata as a string
	    this._saveComponent = function( msg ) {
	      var cell = this._getMsgCell( msg );
	      var md = Jupyter.notebook.metadata;
	      if ( cell ) {
	        if ( !md.react_comms ) {
	          md.react_comms = {}
	        }
	        md.react_comms[ comm.comm_id ] = this._getCellIndex( cell.cell_id ) + '';
	      }
	      this.renderComponent( msg );
	    };

	    // create reacte element and call _render 
	    this.renderComponent = function ( msg, newProps ) {
	      newProps = newProps || props.content.data;
	      newProps.cell = this._getMsgCell( msg );
	      newProps.comm = comm;
	      var element = this._createMarkup( options.components[ this.module ], newProps );
	      this._render( element, msg );
	    };

	    // Render the component to either the output cell or given domId
	    this._render = function ( element, msg ) {
	      var display;
	      if ( this.domId ) {
	        display = document.getElementById( this.domId );
	      } else {
	        display = this._outputAreaElement( msg );
	      }
	      ReactDom.render( element, display );
	    };

	    this.render = function( ) {
	      var newProps = props.content.data;
	      newProps.cell = this.cell;
	      newProps.comm = comm;
	      var element = this._createMarkup( options.components[ this.module ], newProps );
	      this._render( element, {} );
	    }

	    this._getCellIndex = function( cell_id ) {
	      var idx;
	      Jupyter.notebook.get_cells().forEach( function( c, i){
	        if ( c.cell_id === cell_id ) {
	          idx = i;
	        }
	      });
	      return idx;
	    };

	    // gets the components cell or 
	    this._getMsgCell = function( msg ) {
	      if ( this.cell ) return this.cell;
	      var msg_id = msg.parent_header.msg_id;
	      this.cell = Jupyter.notebook.get_msg_cell( msg_id );
	      return this.cell;
	    };

	    // Create React Elements from components and props 
	    this._createMarkup = function ( component, cProps ) {
	      return React.createElement( component, cProps );
	    };

	    // Get the DOM Element to render to
	    this._outputAreaElement = function (msg) {
	      var cell = this._getMsgCell( msg );
	      return cell.react_dom.subarea;
	    };

	    // register message callback
	    this.comm.on_msg(this.handleMsg);
	    return this;
	  };
	};

	/* WEBPACK VAR INJECTION */}.call(exports, __webpack_require__(5)(module)))

/***/ },
/* 5 */
/***/ function(module, exports) {

	module.exports = function(module) {
		if(!module.webpackPolyfill) {
			module.deprecate = function() {};
			module.paths = [];
			// module.parent = undefined by default
			module.children = [];
			module.webpackPolyfill = 1;
		}
		return module;
	}


/***/ },
/* 6 */
/***/ function(module, exports, __webpack_require__) {

	// style-loader: Adds some css to the DOM by adding a <style> tag

	// load the styles
	var content = __webpack_require__(7);
	if(typeof content === 'string') content = [[module.id, content, '']];
	// add the styles to the DOM
	var update = __webpack_require__(9)(content, {});
	if(content.locals) module.exports = content.locals;
	// Hot Module Replacement
	if(false) {
		// When the styles change, update the <style> tags
		if(!content.locals) {
			module.hot.accept("!!./../../node_modules/css-loader/index.js!./../../node_modules/less-loader/index.js!./timbr_machine.less", function() {
				var newContent = require("!!./../../node_modules/css-loader/index.js!./../../node_modules/less-loader/index.js!./timbr_machine.less");
				if(typeof newContent === 'string') newContent = [[module.id, newContent, '']];
				update(newContent);
			});
		}
		// When the module is disposed, remove the <style> tags
		module.hot.dispose(function() { update(); });
	}

/***/ },
/* 7 */
/***/ function(module, exports, __webpack_require__) {

	exports = module.exports = __webpack_require__(8)();
	// imports


	// module
	exports.push([module.id, ".machinestat {\n  position: relative;\n}\n.machinestat .machinestat-status {\n  position: absolute;\n  top: 0;\n  right: 0;\n  font-size: 11.7px;\n}\n.machinestat .machinestat-status:before {\n  content: '';\n  display: inline-block;\n  width: 10px;\n  height: 10px;\n  background: #333333;\n  border-radius: 100%;\n  vertical-align: -1px;\n  margin-right: 2px;\n}\n.machinestat .machinestat-status.machinestat-status-running {\n  color: #98c000;\n}\n.machinestat .machinestat-status.machinestat-status-running:before {\n  background: #98c000;\n}\n.machinestat .machinestat-status.machinestat-status-paused {\n  color: #fbc000;\n}\n.machinestat .machinestat-status.machinestat-status-paused:before {\n  background: #fbc000;\n}\n.machinestat .machinestat-status.machinestat-status-stopped {\n  color: #cccccc;\n}\n.machinestat .machinestat-status.machinestat-status-stopped:before {\n  background: #cccccc;\n}\n.machinestat .machinestat-row {\n  *zoom: 1;\n}\n.machinestat .machinestat-row:before,\n.machinestat .machinestat-row:after {\n  display: table;\n  line-height: 0;\n  content: \"\";\n}\n.machinestat .machinestat-row:after {\n  clear: both;\n}\n.machinestat .machinestat-row .machinestat-performance {\n  float: left;\n  width: 35%;\n  padding-right: 12px;\n}\n.machinestat .machinestat-row .machinestat-meta {\n  float: left;\n  width: 65%;\n  padding-left: 12px;\n  text-align: right;\n}\n.machinestat .machinestat-progress {\n  position: relative;\n}\n.machinestat .machinestat-progress .machinestat-progress-key {\n  display: block;\n  *zoom: 1;\n}\n.machinestat .machinestat-progress .machinestat-progress-key:before,\n.machinestat .machinestat-progress .machinestat-progress-key:after {\n  display: table;\n  line-height: 0;\n  content: \"\";\n}\n.machinestat .machinestat-progress .machinestat-progress-key:after {\n  clear: both;\n}\n.machinestat .machinestat-progress .machinestat-progress-key ul {\n  display: block;\n  list-style-type: none;\n  margin: 0;\n  padding: 0;\n  float: right;\n}\n.machinestat .machinestat-progress .machinestat-progress-key li {\n  float: left;\n  margin-left: 12px;\n}\n.machinestat .machinestat-progress .machinestat-progress-key li[class*=key-]:before {\n  content: '';\n  display: inline-block;\n  width: 11px;\n  height: 11px;\n  margin-right: 4px;\n  vertical-align: -1px;\n}\n.machinestat .machinestat-progress .machinestat-progress-key li.key-queued:before {\n  background: #e7e7e7;\n}\n.machinestat .machinestat-progress .machinestat-progress-key li.key-processed:before {\n  background: #98c000;\n}\n.machinestat .machinestat-progress .machinestat-progress-key li.key-average:before {\n  background: #fbc000;\n}\n.machinestat .machinestat-progress .machinestat-progress-graph {\n  position: relative;\n  width: 100%;\n  height: 32px;\n  background: #e7e7e7;\n}\n.machinestat .machinestat-progress .machinestat-progress-graph .machinestat-progress-processed {\n  height: 32px;\n  width: 0;\n  background: #98c000;\n}\n.machinestat .machinestat-progress .machinestat-progress-graph .machinestat-progress-average {\n  position: absolute;\n  top: 0;\n  left: 0;\n  bottom: 0;\n  width: 2px;\n  background: #fbc000;\n}\n.machinestat .machinestat-progress .machinestat-progress-graph .machinestat-progress-label-queued,\n.machinestat .machinestat-progress .machinestat-progress-graph .machinestat-progress-label-processed {\n  opacity: 0.5;\n  font-size: 11.7px;\n  line-height: 1;\n}\n.machinestat .machinestat-progress .machinestat-progress-graph .machinestat-progress-label-processed {\n  position: absolute;\n  left: 4px;\n  bottom: 4px;\n}\n.machinestat .machinestat-progress .machinestat-progress-graph .machinestat-progress-label-queued {\n  position: absolute;\n  right: 4px;\n  bottom: 4px;\n}\n.machinestat .machinestat-movedown {\n  margin-top: 12px;\n}\n.machinestat .btn {\n  padding: 1px 28px;\n  border: none;\n}\n.machinestat .machinestat-label {\n  font-size: 11.7px;\n  line-height: 1;\n  margin: 12px 0 4px;\n}\n.machinestat .machinestat-sparkline {\n  width: 210px;\n  height: 32px;\n  /*background: #efefef;*/\n}\n.machinestat .machinestat-sparkline .sparkcirle {\n  fill: #98c000;\n}\n", ""]);

	// exports


/***/ },
/* 8 */
/***/ function(module, exports) {

	/*
		MIT License http://www.opensource.org/licenses/mit-license.php
		Author Tobias Koppers @sokra
	*/
	// css base code, injected by the css-loader
	module.exports = function() {
		var list = [];

		// return the list of modules as css string
		list.toString = function toString() {
			var result = [];
			for(var i = 0; i < this.length; i++) {
				var item = this[i];
				if(item[2]) {
					result.push("@media " + item[2] + "{" + item[1] + "}");
				} else {
					result.push(item[1]);
				}
			}
			return result.join("");
		};

		// import a list of modules into the list
		list.i = function(modules, mediaQuery) {
			if(typeof modules === "string")
				modules = [[null, modules, ""]];
			var alreadyImportedModules = {};
			for(var i = 0; i < this.length; i++) {
				var id = this[i][0];
				if(typeof id === "number")
					alreadyImportedModules[id] = true;
			}
			for(i = 0; i < modules.length; i++) {
				var item = modules[i];
				// skip already imported module
				// this implementation is not 100% perfect for weird media query combinations
				//  when a module is imported multiple times with different media queries.
				//  I hope this will never occur (Hey this way we have smaller bundles)
				if(typeof item[0] !== "number" || !alreadyImportedModules[item[0]]) {
					if(mediaQuery && !item[2]) {
						item[2] = mediaQuery;
					} else if(mediaQuery) {
						item[2] = "(" + item[2] + ") and (" + mediaQuery + ")";
					}
					list.push(item);
				}
			}
		};
		return list;
	};


/***/ },
/* 9 */
/***/ function(module, exports, __webpack_require__) {

	/*
		MIT License http://www.opensource.org/licenses/mit-license.php
		Author Tobias Koppers @sokra
	*/
	var stylesInDom = {},
		memoize = function(fn) {
			var memo;
			return function () {
				if (typeof memo === "undefined") memo = fn.apply(this, arguments);
				return memo;
			};
		},
		isOldIE = memoize(function() {
			return /msie [6-9]\b/.test(window.navigator.userAgent.toLowerCase());
		}),
		getHeadElement = memoize(function () {
			return document.head || document.getElementsByTagName("head")[0];
		}),
		singletonElement = null,
		singletonCounter = 0,
		styleElementsInsertedAtTop = [];

	module.exports = function(list, options) {
		if(false) {
			if(typeof document !== "object") throw new Error("The style-loader cannot be used in a non-browser environment");
		}

		options = options || {};
		// Force single-tag solution on IE6-9, which has a hard limit on the # of <style>
		// tags it will allow on a page
		if (typeof options.singleton === "undefined") options.singleton = isOldIE();

		// By default, add <style> tags to the bottom of <head>.
		if (typeof options.insertAt === "undefined") options.insertAt = "bottom";

		var styles = listToStyles(list);
		addStylesToDom(styles, options);

		return function update(newList) {
			var mayRemove = [];
			for(var i = 0; i < styles.length; i++) {
				var item = styles[i];
				var domStyle = stylesInDom[item.id];
				domStyle.refs--;
				mayRemove.push(domStyle);
			}
			if(newList) {
				var newStyles = listToStyles(newList);
				addStylesToDom(newStyles, options);
			}
			for(var i = 0; i < mayRemove.length; i++) {
				var domStyle = mayRemove[i];
				if(domStyle.refs === 0) {
					for(var j = 0; j < domStyle.parts.length; j++)
						domStyle.parts[j]();
					delete stylesInDom[domStyle.id];
				}
			}
		};
	}

	function addStylesToDom(styles, options) {
		for(var i = 0; i < styles.length; i++) {
			var item = styles[i];
			var domStyle = stylesInDom[item.id];
			if(domStyle) {
				domStyle.refs++;
				for(var j = 0; j < domStyle.parts.length; j++) {
					domStyle.parts[j](item.parts[j]);
				}
				for(; j < item.parts.length; j++) {
					domStyle.parts.push(addStyle(item.parts[j], options));
				}
			} else {
				var parts = [];
				for(var j = 0; j < item.parts.length; j++) {
					parts.push(addStyle(item.parts[j], options));
				}
				stylesInDom[item.id] = {id: item.id, refs: 1, parts: parts};
			}
		}
	}

	function listToStyles(list) {
		var styles = [];
		var newStyles = {};
		for(var i = 0; i < list.length; i++) {
			var item = list[i];
			var id = item[0];
			var css = item[1];
			var media = item[2];
			var sourceMap = item[3];
			var part = {css: css, media: media, sourceMap: sourceMap};
			if(!newStyles[id])
				styles.push(newStyles[id] = {id: id, parts: [part]});
			else
				newStyles[id].parts.push(part);
		}
		return styles;
	}

	function insertStyleElement(options, styleElement) {
		var head = getHeadElement();
		var lastStyleElementInsertedAtTop = styleElementsInsertedAtTop[styleElementsInsertedAtTop.length - 1];
		if (options.insertAt === "top") {
			if(!lastStyleElementInsertedAtTop) {
				head.insertBefore(styleElement, head.firstChild);
			} else if(lastStyleElementInsertedAtTop.nextSibling) {
				head.insertBefore(styleElement, lastStyleElementInsertedAtTop.nextSibling);
			} else {
				head.appendChild(styleElement);
			}
			styleElementsInsertedAtTop.push(styleElement);
		} else if (options.insertAt === "bottom") {
			head.appendChild(styleElement);
		} else {
			throw new Error("Invalid value for parameter 'insertAt'. Must be 'top' or 'bottom'.");
		}
	}

	function removeStyleElement(styleElement) {
		styleElement.parentNode.removeChild(styleElement);
		var idx = styleElementsInsertedAtTop.indexOf(styleElement);
		if(idx >= 0) {
			styleElementsInsertedAtTop.splice(idx, 1);
		}
	}

	function createStyleElement(options) {
		var styleElement = document.createElement("style");
		styleElement.type = "text/css";
		insertStyleElement(options, styleElement);
		return styleElement;
	}

	function createLinkElement(options) {
		var linkElement = document.createElement("link");
		linkElement.rel = "stylesheet";
		insertStyleElement(options, linkElement);
		return linkElement;
	}

	function addStyle(obj, options) {
		var styleElement, update, remove;

		if (options.singleton) {
			var styleIndex = singletonCounter++;
			styleElement = singletonElement || (singletonElement = createStyleElement(options));
			update = applyToSingletonTag.bind(null, styleElement, styleIndex, false);
			remove = applyToSingletonTag.bind(null, styleElement, styleIndex, true);
		} else if(obj.sourceMap &&
			typeof URL === "function" &&
			typeof URL.createObjectURL === "function" &&
			typeof URL.revokeObjectURL === "function" &&
			typeof Blob === "function" &&
			typeof btoa === "function") {
			styleElement = createLinkElement(options);
			update = updateLink.bind(null, styleElement);
			remove = function() {
				removeStyleElement(styleElement);
				if(styleElement.href)
					URL.revokeObjectURL(styleElement.href);
			};
		} else {
			styleElement = createStyleElement(options);
			update = applyToTag.bind(null, styleElement);
			remove = function() {
				removeStyleElement(styleElement);
			};
		}

		update(obj);

		return function updateStyle(newObj) {
			if(newObj) {
				if(newObj.css === obj.css && newObj.media === obj.media && newObj.sourceMap === obj.sourceMap)
					return;
				update(obj = newObj);
			} else {
				remove();
			}
		};
	}

	var replaceText = (function () {
		var textStore = [];

		return function (index, replacement) {
			textStore[index] = replacement;
			return textStore.filter(Boolean).join('\n');
		};
	})();

	function applyToSingletonTag(styleElement, index, remove, obj) {
		var css = remove ? "" : obj.css;

		if (styleElement.styleSheet) {
			styleElement.styleSheet.cssText = replaceText(index, css);
		} else {
			var cssNode = document.createTextNode(css);
			var childNodes = styleElement.childNodes;
			if (childNodes[index]) styleElement.removeChild(childNodes[index]);
			if (childNodes.length) {
				styleElement.insertBefore(cssNode, childNodes[index]);
			} else {
				styleElement.appendChild(cssNode);
			}
		}
	}

	function applyToTag(styleElement, obj) {
		var css = obj.css;
		var media = obj.media;

		if(media) {
			styleElement.setAttribute("media", media)
		}

		if(styleElement.styleSheet) {
			styleElement.styleSheet.cssText = css;
		} else {
			while(styleElement.firstChild) {
				styleElement.removeChild(styleElement.firstChild);
			}
			styleElement.appendChild(document.createTextNode(css));
		}
	}

	function updateLink(linkElement, obj) {
		var css = obj.css;
		var sourceMap = obj.sourceMap;

		if(sourceMap) {
			// http://stackoverflow.com/a/26603875
			css += "\n/*# sourceMappingURL=data:application/json;base64," + btoa(unescape(encodeURIComponent(JSON.stringify(sourceMap)))) + " */";
		}

		var blob = new Blob([css], { type: "text/css" });

		var oldSrc = linkElement.href;

		linkElement.href = URL.createObjectURL(blob);

		if(oldSrc)
			URL.revokeObjectURL(oldSrc);
	}


/***/ }
/******/ ])});;
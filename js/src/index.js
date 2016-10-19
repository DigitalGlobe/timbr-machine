import JupyterReact from 'jupyter-react-js';

let components = null;

try {
  components = require( '@timbr/react-machine' );
} catch ( error ) {
  console.error( error );
}

function load_ipython_extension () {
  requirejs([
      "base/js/namespace",
      "base/js/events",
  ], function( Jupyter, events ) {
      // initialize jupyter react cells, comm mananger and components
      const on_update = ( module, props, commId ) => {
        components.dispatcher.dispatch({
          actionType: module.toLowerCase() + '_update',
          data: Object.assign({}, props, { commId: commId }),
          commId
        });
      }
      JupyterReact.init( Jupyter, events, 'timbr.machine', { components, on_update } );
  });
}

module.exports = {
  load_ipython_extension: load_ipython_extension
};
